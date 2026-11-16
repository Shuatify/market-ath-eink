import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from build import compute_card, market_window, demo_cards, render

ET = ZoneInfo('America/New_York')


class Tests(unittest.TestCase):
    def test_intraday_breakout_preserves_previous_ath_age(self):
        card = compute_card('QQQ', 'test', [(date(2026, 8, 1), 100)], 105,
                            datetime(2026, 11, 13, 14, 15, tzinfo=ET), '5M BAR')
        self.assertTrue(card.is_breakout)
        self.assertAlmostEqual(card.change, 5)
        self.assertEqual(card.days, 104)
        self.assertEqual(card.reference_ath, 100)

    def test_no_new_high(self):
        card = compute_card('QQQ', 'test', [(date(2026, 11, 10), 100)], 82,
                            datetime(2026, 11, 13, 14, 15, tzinfo=ET), '5M BAR')
        self.assertFalse(card.is_breakout)
        self.assertAlmostEqual(card.change, -18)
        self.assertEqual(card.days, 3)

    def test_new_day_resets_reference_to_prior_closing_ath(self):
        today = datetime(2026, 11, 13, 14, 15, tzinfo=ET)
        card = compute_card('QQQ', 'test', [(date(2026, 11, 10), 100), (date(2026, 11, 12), 105)],
                            104, today, '5M BAR')
        self.assertAlmostEqual(card.change, 100 * (104/105-1))
        self.assertEqual(card.days, 1)

    def test_market_holiday_and_early_close(self):
        self.assertFalse(market_window(datetime(2026, 11, 26, 11, 0, tzinfo=ET)))  # Thanksgiving
        self.assertTrue(market_window(datetime(2026, 11, 27, 12, 45, tzinfo=ET)))  # 13:00 close
        self.assertTrue(market_window(datetime(2026, 11, 27, 13, 20, tzinfo=ET)))
        self.assertFalse(market_window(datetime(2026, 11, 27, 14, 0, tzinfo=ET)))

    def test_demo_marks_fictional_data(self):
        page = render(demo_cards(), demo=True)
        self.assertIn('DEMO · SAMPLE DATA', page)
        self.assertIn('BREAKOUT', page)
        self.assertIn('800px;height:480px', page)

if __name__ == '__main__':
    unittest.main()
