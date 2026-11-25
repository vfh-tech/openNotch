import unittest

from notch_state import Banner, NotchState, Page


class NotchStateTests(unittest.TestCase):
    def setUp(self):
        self.state = NotchState(output=True)
        self.notice = Banner('Mail', 'Message', 'Body')

    def test_banner_owns_view_until_dismissed(self):
        self.state.hover = True
        self.state.show(self.notice)
        self.assertIs(self.state.page, Page.BANNER)
        self.state.dismiss()
        self.assertIs(self.state.page, Page.TRAY)
        self.state.hover = False
        self.assertIs(self.state.page, Page.CLOSED)

    def test_losing_output_clears_holds_but_preserves_current_banner(self):
        self.state.hover = True
        self.state.menu = True
        self.state.drag = True
        self.state.show(self.notice)
        self.state.set_output(False)
        self.assertIs(self.state.page, Page.UNAVAILABLE)
        self.state.set_output(True)
        self.assertIs(self.state.page, Page.BANNER)
        self.state.dismiss()
        self.assertIs(self.state.page, Page.CLOSED)

    def test_drag_hold_keeps_tray_open_without_hover(self):
        self.state.drag = True
        self.assertIs(self.state.page, Page.TRAY)
        self.state.drag = False
        self.assertIs(self.state.page, Page.CLOSED)
