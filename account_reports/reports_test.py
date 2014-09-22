# -*- coding: utf-8 -*-
import datetime
import mock

from unittest import TestCase

from .reports import (
    Account, AccountReport, active_non_trial, TwoPeriodReport,
    TablePrinter
)


class AccountClassTests(TestCase):
    def test_is_active(self):
        account = Account({'Active': 'True'})
        assert account.is_active

        account = Account({'Active': 'asdf'})
        assert not account.is_active

    def test_is_free(self):
        account = Account({'Plan Code': 'free'})
        assert account.is_free

        account = Account({'Plan Code': 'Seat9'})
        assert not account.is_free

    def test_id(self):
        account = Account({'Account ID': '1234'})
        assert '1234' == account.id

    def test_out_of_trial(self):
        account = Account({'Created': '2014-03-15 12:00:00+00:00'})
        assert account.out_of_trial(datetime.datetime(2014, 7, 15))

    def test_registered_out_of_range(self):
        account = Account({'Created': '2014-03-15 12:00:00+00:00'})
        assert account.registered_out_of_range(datetime.datetime(2014, 2, 1))


def genAccount(id_num, plan='small', active=True, in_trial=False):
    a = Account()
    a['Account ID'] = id_num
    if in_trial:
        d = datetime.datetime.now() - datetime.timedelta(days=2)
    else:
        d = datetime.datetime.now() - datetime.timedelta(days=40)
    a['Created'] = datetime.datetime.strftime(d, '%Y-%m-%d %H:%M:%S+00:00')
    a['Plan Code'] = plan
    a['Active'] = active

    return a


class AccountReportClassTest(TestCase):
    def test_getitem(self):
        report = AccountReport('foo', 'bar')
        assert set() == report['in_trial']

    def test_init(self):
        report = AccountReport('foo', report='bar')
        assert 'foo' == report.period
        assert 'bar' == report.report


class ActiveNonTrialTests(TestCase):
    def test_active_non_trial(self):
        active1 = genAccount(1, in_trial=True)
        active2 = genAccount(2, plan='free')
        inactive = genAccount(3, active=False)

        old = {}
        old['active'] = set([active1.id, active2.id])
        old['free'] = set([active2.id])
        old['paid'] = set([active1.id, inactive.id])
        old['in_trial'] = set([active1.id])

        assert active_non_trial(old) == set([2])

class AccountReportTests(TestCase):
    pass


def genReport(active=None, free=None, paid=None, in_trial=None, period=None):
    report = AccountReport(period or datetime.datetime.now())
    report.results['active'] = set(active or [])
    report.results['free'] = set(free or [])
    report.results['paid'] = set(paid or [])
    report.results['in_trial'] = set(in_trial or [])
    return report


class TwoPeriodReportTests(TestCase):
    def test_date(self):
        old = genReport(
            period=datetime.datetime(2011, 2, 4, 0, 0, 0),
            active=[1],
            free=[1])

        new = genReport(
            period=datetime.datetime(2011, 3, 4, 0, 0, 0),
            active=[1, 2],
            free=[1, 2])

        report = TwoPeriodReport(old, new)

        assert report.date == old.period

    def test_new_free(self):
        old = genReport(
            active=[1],
            free=[1])

        new = genReport(
            active=[1, 2],
            free=[1, 2])

        report = TwoPeriodReport(old, new)

        assert report.new_free() == set([2])

    def test_new_accounts(self):
        old = genReport(in_trial=[1, 2, 3])
        new = genReport(in_trial=[3, 4, 5])

        report = TwoPeriodReport(old, new)

        assert report.new_accounts() == set([4, 5])

    def test_new_paid(self):
        old = genReport(paid=[1, 2, 3],
                        active=[1, 2, 3])
        new = genReport(paid=[3, 4],
                        active=[3, 4])

        report = TwoPeriodReport(old, new)

        assert report.new_paid() == set([4])

    def test_free_at_eom(self):
        old = genReport(free=[1, 2])
        new = genReport(free=[1, 2, 3])

        report = TwoPeriodReport(old, new)

        assert len(report.free_at_eom()) == 3

    def test_paid_to_free(self):
        old = genReport(paid=[1, 2],
                        active=[1, 2])

        new = genReport(paid=[1],
                        free=[2],
                        active=[1, 2])

        report = TwoPeriodReport(old, new)

        assert report.paid_to_free() == set([2])

    def test_free_to_paid(self):
        old = genReport(free=[1, 2],
                        active=[1, 2])

        new = genReport(free=[1],
                        paid=[2],
                        active=[1, 2])

        report = TwoPeriodReport(old, new)

        assert report.free_to_paid() == set([2])


class TableTests(TestCase):
    """
    Note: These tests dig into the internal state of the PrettyTable class to
    avoid having to validate against printed output.
    """
    def setUp(self):
        old = mock.Mock()
        old.date = datetime.datetime(2011, 04, 01, 0, 0, 0)
        old.new_accounts.return_value = range(4)
        old.new_free.return_value = range(10)
        old.new_paid.return_value = range(3)
        old.free_at_eom.return_value = range(2)
        old.paid_to_free.return_value = range(1)
        old.free_to_paid.return_value = range(5)

        new = mock.Mock()
        new.date = datetime.datetime(2011, 05, 01, 0, 0, 0)
        new.new_accounts.return_value = range(7)
        new.new_free.return_value = range(12)
        new.new_paid.return_value = range(4)
        new.free_at_eom.return_value = range(3)
        new.paid_to_free.return_value = range(2)
        new.free_to_paid.return_value = range(6)

        self.old = old
        self.new = new

    def test_headers(self):
        tp = TablePrinter(self.old, self.new)

        assert ['', 'Apr 2011', 'May 2011', 'Change'] == tp.table._field_names

    def test_rows(self):
        tp = TablePrinter(self.old, self.new)
        assert tp.table._rows == [
            ['New Accounts', 4, 7, ''],
            ['New Free', 10, 12, ''],
            ['New Paid', 3, 4, ''],
            ['Total Free @ EOM', 2, 3, '50.00%'],
            ['Paid to Free*', 1, 2, ''],
            ['Free to Paid*', 5, 6, ''],
        ]
