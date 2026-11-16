"""Run with: uv run python -m unittest tests.test_indicator"""

import unittest

from filets.indicator import EmergenceIndicator, extract_rules

INES = ("I think we should aim to catch at most 8 tons this season, so the lake can replenish "
        "its resources and ensure a healthy catch for next year. I plan to catch 5 tons myself.")
TOMAS = ("Nils, I agree with Ines that we should aim to catch at most 8 tons this season. "
         "I plan to catch 8 tons myself, so we can replenish the lake's resources and ensure "
         "a healthy catch for next year.")
NILS = ("I concur with Ines that we should aim to catch at most 8 tons this season, to ensure "
        "the lake's replenishment and a healthy catch for next year. I plan to catch 5 tons "
        "myself, in line with Ines's plan and to help my family.")
MARA = ("I concur with Ines and Nils, let's aim to catch as much as we can this season, but "
        "I'll need to catch more than 5 tons to sustain my family, so I plan to catch 10 tons "
        "myself this season.")


def close_season(spoken: list[tuple[str, float]], requested: list[float], safe_total: float,
                 caught: list[float] | None = None, hint: bool = True) -> dict:
    indicator = EmergenceIndicator()
    indicator.add({"type": "run_started", "run": "test", "agents": len(requested), "hint": hint})
    for agent, (text, planned) in enumerate(spoken):
        indicator.add({"type": "message", "season": 1, "agent": agent, "text": text, "planned_catch": planned})
    for agent, tons in enumerate(requested):
        indicator.add({"type": "decision", "season": 1, "agent": agent, "requested": tons})
    for agent, tons in enumerate(caught if caught is not None else requested):
        indicator.add({"type": "catch", "season": 1, "agent": agent, "caught": tons})
    return indicator.add({"type": "lake", "season": 1, "safe_total": safe_total})


class Rules(unittest.TestCase):
    def test_own_plan_above_a_fair_share_means_per_person(self):
        self.assertEqual(extract_rules(INES, 5.0, 4), {("each", 8.0)})
        self.assertEqual(extract_rules("Let's take no more than 12 tons.", 4.0, 4), {("each", 12.0)})

    def test_own_plan_within_a_fair_share_means_total(self):
        self.assertEqual(extract_rules("Let's take no more than 12 tons.", 3.0, 4), {("total", 12.0)})
        self.assertEqual(extract_rules("It would help us to catch under 12 tons.", 2.0, 4), {("total", 12.0)})

    def test_words_beat_the_plan(self):
        self.assertEqual(extract_rules("We should catch at most 20 tons in total.", 8.0, 4), {("total", 20.0)})
        for text in ("We should catch 5 tons each.", "We should each catch at most 5 tons.",
                     "Let's catch at most 5 tons per fisher.", "We should catch at most 5 tons per person.",
                     "If we agree, we can all take 5 tons."):
            self.assertEqual(extract_rules(text, 1.0, 4), {("each", 5.0)}, text)

    def test_personal_plan_is_no_rule(self):
        self.assertEqual(extract_rules("I plan to catch 5 tons.", 5.0, 4), set())


class SeasonThree(unittest.TestCase):
    """Season 3 of run 20261102-125217_talk_llama3.2-3b_s1, from its log."""

    def test_record(self):
        record = close_season([(MARA, 10.0), (NILS, 5.0), (TOMAS, 8.0), (INES, 5.0)],
                              [10.0, 5.0, 8.0, 5.0], 8.060604875000003)
        self.assertEqual(record["rule"], "8 tons each")
        self.assertEqual(record["rule_limit"], 8.0)
        self.assertFalse(record["echoes_hint"])
        self.assertTrue(record["misread_hint"])
        self.assertEqual(record["respect_share"], 0.75)
        self.assertTrue(record["holds"]["respect"])
        self.assertTrue(record["hint_derived"])
        self.assertFalse(record["misread_baseline"])


class GroupRules(unittest.TestCase):
    RULE = "We should catch at most 20 tons in total."

    def season(self, planned: list[float], caught: list[float]) -> dict:
        return close_season([(self.RULE, tons) for tons in planned], caught, 30.0)

    def test_sum_within_the_total_passes_despite_unequal_shares(self):
        record = self.season([8.0, 4.0, 4.0, 4.0], [8.0, 4.0, 4.0, 4.0])
        self.assertEqual(record["rule_limit"], 20.0)
        self.assertEqual(record["announced_within"], 4)
        self.assertEqual(record["respect_share"], 1.0)

    def test_sum_above_the_total_fails_everyone(self):
        record = self.season([5.0, 5.0, 5.0, 5.0], [5.0, 5.0, 5.0, 6.0])
        self.assertEqual(record["announced_within"], 4)
        self.assertEqual(record["respect_share"], 0.0)
        self.assertFalse(record["holds"]["respect"])

    def test_announced_sum_is_checked_on_its_own(self):
        record = self.season([6.0, 6.0, 6.0, 6.0], [5.0, 5.0, 5.0, 5.0])
        self.assertEqual(record["announced_within"], 0)
        self.assertFalse(record["holds"]["announced"])
        self.assertTrue(record["holds"]["respect"])

    def test_unequal_announcements_pass_when_their_sum_keeps_the_total(self):
        record = self.season([12.0, 4.0, 2.0, 2.0], [12.0, 4.0, 2.0, 2.0])
        self.assertGreater(record["announced_spread"], 1.5)
        self.assertTrue(record["holds"]["announced"])


class Respect(unittest.TestCase):
    RULE = "We should catch at most 5 tons each."

    def test_rationing_is_not_restraint(self):
        """Asking for 9 tons breaks a 5-ton rule even if an empty lake gave only 4."""
        record = close_season([(self.RULE, 5.0)] * 4, [9.0, 9.0, 5.0, 5.0], 30.0,
                              caught=[4.0, 4.0, 4.0, 4.0])
        self.assertEqual(record["caught_sum"], 16.0)
        self.assertEqual(record["requested_sum"], 28.0)
        self.assertEqual(record["respect_share"], 0.5)
        self.assertFalse(record["holds"]["respect"])


class SeasonKind(unittest.TestCase):
    def test_one_kind_per_season_by_majority_of_plans(self):
        """Unmarked "8 tons": three plan above a fair share of 2, so all four count as "each"."""
        text = "Let's catch at most 8 tons."
        record = close_season([(text, 5.0), (text, 6.0), (text, 4.0), (text, 1.0)], [5.0, 6.0, 4.0, 1.0], 30.0)
        self.assertEqual(record["rule"], "8 tons each")
        self.assertEqual(record["mention_share"], 1.0)

    def test_a_word_counts_as_its_speakers_vote(self):
        marked = "We should catch at most 8 tons in total."
        plain = "Let's catch at most 8 tons."
        record = close_season([(marked, 3.0), (marked, 3.0), (plain, 5.0), (plain, 1.0)], [3, 3, 1, 1], 30.0)
        self.assertEqual(record["rule"], "8 tons in total")

    def test_a_tie_goes_to_the_mean_plan(self):
        text = "Let's catch at most 8 tons."
        record = close_season([(text, 4.0), (text, 4.0), (text, 1.0), (text, 1.0)], [4, 4, 1, 1], 30.0)
        self.assertEqual(record["rule"], "8 tons each")  # mean plan 2.5 > fair share 2


class ChanceBaseline(unittest.TestCase):
    def test_no_hint_run_still_measures_a_misread(self):
        record = close_season([(INES, 5.0), (NILS, 5.0), (TOMAS, 8.0), ("", 3.0)], [5, 5, 8, 3], 8.06,
                              hint=False)
        self.assertTrue(record["misread_hint"])
        self.assertTrue(record["misread_baseline"])
        self.assertFalse(record["echoes_hint"])
        self.assertFalse(record["hint_derived"])


if __name__ == "__main__":
    unittest.main()
