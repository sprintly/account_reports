import csv
import datetime

from boto.s3.connection import S3Connection
from boto.s3.key import Key
from prettytable import PrettyTable
from collections import defaultdict
from pprint import pprint

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class Account(dict):
    @property
    def is_active(self):
        return self['Active'] == 'True'

    @property
    def is_free(self):
        return 'free' in self['Plan Code']

    def out_of_trial(self, date):
        return datetime.datetime.strptime(self['Created'],
            '%Y-%m-%d %H:%M:%S+00:00') + datetime.timedelta(days=30) < date

    def registered_out_of_range(self, date):
        return datetime.datetime.strptime(self['Created'],
            '%Y-%m-%d %H:%M:%S+00:00') >= date

    @property
    def id(self):
        return self['Account ID']


class AccountReport(object):
    def __init__(self, period, report=None):
        self.period = period
        self.report = report
        self.results = {
            'in_trial': set(),
            'paid': set(),
            'free': set(),
            'active': set()
        }
        self.account_map = {}

    def evaluate(self):
        for row in self.report:
            account = Account(row)
            self.account_map[account.id] = account
            if account.registered_out_of_range(self.period):
                continue

            if not account.out_of_trial(self.period):
                self.results['in_trial'].add(account.id)
                continue

            if account.is_active:
                self.results['active'].add(account.id)

            if account.is_free:
                self.results['free'].add(account.id)
            else:
                self.results['paid'].add(account.id)

    def __getitem__(self, key):
        return self.results[key]


def get_report(month, key, secret):
    # Fetch the report from S3.
    conn = S3Connection(key, secret)
    bucket = conn.get_bucket('sprintly-daily-account-csv')
    key = Key(bucket, month.strftime('accounts-%Y%m%d.csv'))
    return csv.DictReader(StringIO(key.get_contents_as_string()))


class TwoPeriodReport(object):
    def __init__(self, old_period, new_period):
        self.old_period = old_period
        self.new_period = new_period

    @property
    def date(self):
        return self.old_period.period

    def new_free(self):
        new = active_non_trial(self.new_period)
        old = active_non_trial(self.old_period)
        return new - old - self.old_period['paid']

    def new_accounts(self):
        """
        Returns the new accounts we got.

        This isn't new paid accounts. Just people who are in trial now that
        weren't before.
        """
        return self.new_period['in_trial'] - self.old_period['in_trial']

    def new_paid(self):
        new = active_non_trial(self.new_period)
        old = active_non_trial(self.old_period)

        return (new - old) - self.new_period['free']

    def free_at_eom(self):
        return self.new_period['free']

    def paid_to_free(self):
        return self.new_period['free'] & self.old_period['paid']

    def free_to_paid(self):
        return self.new_period['paid'] & self.old_period['free']


def active_non_trial(account_set):
    return account_set['active'] & (
        account_set['free'] | account_set['paid']) - account_set['in_trial']


class TablePrinter(object):
    def __init__(self, old, new, header_format='%b %Y'):
        table = PrettyTable(["",
            old.date.strftime(header_format),
            new.date.strftime(header_format),
            "Change"])
        table.align[''] = 'r'
        table.align[new.date.strftime(header_format)] = 'r'
        table.align[old.date.strftime(header_format)] = 'r'
        table.align["Change"] = 'r'

        table.add_row(["New Accounts",
                       len(old.new_accounts()),
                       len(new.new_accounts()),
                       ""])
        table.add_row(["New Free",
                       len(old.new_free()),
                       len(new.new_free()),
                       ""])
        table.add_row(["New Paid",
                       len(old.new_paid()),
                       len(new.new_paid()),
                       ""])

        amt_free_old = len(old.free_at_eom())
        amt_free_new = len(new.free_at_eom())
        net = float(amt_free_new) - float(amt_free_old)
        change = net / float(amt_free_old) * 100

        table.add_row(["Total Free @ EOM",
                       amt_free_old,
                       amt_free_new,
                       "%.2f%%" % change])
        table.add_row(["Paid to Free*",
                       len(old.paid_to_free()),
                       len(new.paid_to_free()),
                       ""])
        table.add_row(["Free to Paid*",
                       len(old.free_to_paid()),
                       len(new.free_to_paid()),
                       ""])

        self.table = table

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return '%s' % self.table


class ReportGenerator(object):
    def __init__(self, period1, period2, period3, list_paid=False,
                 plan_breakdown=False, key=None, secret=None, header_format=None):
        if key is None:
            raise AttributeError("Must provide AWS key")

        if secret is None:
            raise AttributeError("Must provide AWS secret")

        prv = AccountReport(period1, get_report(period1, key, secret))
        old = AccountReport(period2, get_report(period2, key, secret))
        new = AccountReport(period3, get_report(period3, key, secret))

        old.evaluate()
        new.evaluate()
        prv.evaluate()

        latest_month = TwoPeriodReport(old, new)
        previous_month = TwoPeriodReport(prv, old)

        table = TablePrinter(previous_month, latest_month,
                             header_format=header_format or '%b %Y')
        print table
        print "* Need to validate."

        if list_paid:
            print "--"

            ids = latest_month.new_paid()

            print "New, paid account ids: %s: " % (', '.join(ids))

        if plan_breakdown:
            new_active_non_trial = active_non_trial(new)
            d = defaultdict(int)
            for acct_id in new_active_non_trial:
                acct = new.account_map[acct_id]
                plan = acct['Plan Code']
                d[plan] += 1

            print pprint(dict(d))
