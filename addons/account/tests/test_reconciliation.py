from openerp.tests.common import TransactionCase
import time

class TestReconciliation(TransactionCase):

    """Tests for reconciliation (account.tax)

    Test used to check that when doing a sale or purchase invoice in a different currency,
    the result will be balanced.
    """

    def setUp(self):
        super(TestReconciliation, self).setUp()
        self.account_invoice_model = self.env['account.invoice']
        self.account_invoice_line_model = self.env['account.invoice.line']
        self.acc_bank_stmt_model = self.env['account.bank.statement']
        self.acc_bank_stmt_line_model = self.env['account.bank.statement.line']

        self.partner_agrolait_id = self.env.ref("base.res_partner_2")
        self.currency_swiss_id = self.env.ref("base.CHF")
        self.currency_usd_id = self.env.ref("base.USD")
        self.currency_euro_id = self.env.ref("base.EUR")
        self.account_rcv_id = self.env.ref("account.a_recv")
        self.account_rsa_id = self.env.ref("account.rsa")
        self.product_id = self.env.ref("product.product_product_4")

        self.bank_journal_usd_id = self.env.ref('account.bank_journal_usd')
        self.account_usd_id = self.env.ref('account.usd_bnk')
        self.bank_journal_euro_id = self.env.ref('account.bank_journal')
        self.account_euro_id = self.env.ref('account.bnk')

        self.company_id = self.env.ref('base.main_company')

        # set expense_currency_exchange_account_id and income_currency_exchange_account_id to a random account
        self.company_id.write({
            'expense_currency_exchange_account_id': self.account_rsa_id.id,
            'income_currency_exchange_account_id': self.account_rsa_id.id
        })

    def create_invoice(self, type='out_invoice', currency=None):
        #we create an invoice in given currency
        invoice = self.account_invoice_model.create({'partner_id': self.partner_agrolait_id,
            'reference_type': 'none',
            'currency_id': currency,
            'name': type == 'out_invoice' and 'invoice to client' or 'invoice to supplier',
            'account_id': self.account_rcv_id,
            'type': type,
            'date_invoice': time.strftime('%Y') + '-07-01',
            })
        self.account_invoice_line_model.create({'product_id': self.product_id,
            'quantity': 1,
            'price_unit': 100,
            'invoice_id': invoice.id,
            'name': 'product that cost 100',
        })

        #validate invoice
        invoice.signal_workflow('invoice_open')
        return invoice

    def make_payment(self, invoice_record, bank_journal, amount=0.0, amount_currency=0.0, currency_id=None):
        bank_stmt_id = self.acc_bank_stmt_model.create({
            'journal_id': bank_journal,
            'date': time.strftime('%Y') + '-07-15',
        })

        bank_stmt_line_id = self.acc_bank_stmt_line_model.create({'name': 'payment',
            'statement_id': bank_stmt_id,
            'partner_id': self.partner_agrolait_id,
            'amount': amount,
            'amount_currency': amount_currency,
            'currency_id': currency_id,
            'date': time.strftime('%Y') + '-07-15',})

        #reconcile the payment with the invoice
        for l in invoice_record.move_id.line_id:
            if l.account_id.id == self.account_rcv_id:
                line_id = l
                break
        amount_in_widget = currency_id and amount_currency or amount
        self.acc_bank_stmt_line_model.process_reconciliation(bank_stmt_line_id, [
            {'counterpart_move_line_id': line_id.id, 'debit': amount_in_widget < 0 and -amount_in_widget or 0.0, 'credit': amount_in_widget > 0 and amount_in_widget or 0.0, 'name': line_id.name,}])
        return bank_stmt_id

    def check_results(self, move_line_ids, aml_dict):
        #we check that the line is balanced (bank statement line)
        self.assertEquals(len(move_line_ids), len(aml_dict))
        for move_line in move_line_ids:
            self.assertEquals(round(move_line.debit, 2), aml_dict[move_line.account_id.id]['debit'])
            self.assertEquals(round(move_line.credit, 2), aml_dict[move_line.account_id.id]['credit'])
            self.assertEquals(round(move_line.amount_currency, 2), aml_dict[move_line.account_id.id]['amount_currency'])
            self.assertEquals(move_line.currency_id.id, aml_dict[move_line.account_id.id]['currency_id'])

    def make_customer_and_supplier_flows(self, invoice_currency, bank_journal, amount, amount_currency, transaction_currency):
        #we create an invoice in given invoice_currency
        invoice_record = self.create_invoice(type='out_invoice', currency=invoice_currency)
        #we encode a payment on it, on the given bank_journal with amount, amount_currency and trasaction_currency given
        bank_stmt_id = self.make_payment(invoice_record, bank_journal, amount=amount, amount_currency=amount_currency, currency_id=transaction_currency)
        customer_move_lines = self.acc_bank_stmt_model.browse(bank_stmt_id).move_line_ids

        #we create a supplier invoice in given invoice_currency
        invoice_record = self.create_invoice(type='in_invoice', currency=invoice_currency)
        #we encode a payment on it, on the given bank_journal with amount, amount_currency and trasaction_currency given
        bank_stmt_id = self.make_payment(invoice_record, bank_journal, amount=-amount, amount_currency=-amount_currency, currency_id=transaction_currency)
        supplier_move_lines = self.acc_bank_stmt_model.browse(bank_stmt_id).move_line_ids
        return customer_move_lines, supplier_move_lines

    def test_statement_usd_invoice_eur_transaction_eur(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_euro_id, self.bank_journal_usd_id, 42, 30, self.currency_euro_id)
        self.check_results(customer_move_lines, {
            self.account_usd_id: {'debit': 30.0, 'credit': 0.0, 'amount_currency': 42, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 30.0, 'amount_currency': -42, 'currency_id': self.currency_usd_id},
        })
        self.check_results(supplier_move_lines, {
            self.account_usd_id: {'debit': 0.0, 'credit': 30.0, 'amount_currency': -42, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 30.0, 'credit': 0.0, 'amount_currency': 42, 'currency_id': self.currency_usd_id},
        })

    def test_statement_usd_invoice_usd_transaction_usd(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_usd_id, self.bank_journal_usd_id, 50, 0, False)
        self.check_results(customer_move_lines, {
            self.account_usd_id: {'debit': 32.70, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 32.70, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
        })
        self.check_results(supplier_move_lines, {
            self.account_usd_id: {'debit': 0.0, 'credit': 32.70, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 32.70, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
        })

    def test_statement_usd_invoice_usd_transaction_eur(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_usd_id, self.bank_journal_usd_id, 50, 40, self.currency_euro_id)
        self.check_results(customer_move_lines, {
            self.account_usd_id: {'debit': 40.0, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 32.70, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
            self.account_rsa_id: {'debit': 0.0, 'credit': 7.30, 'amount_currency': 0.0, 'currency_id': self.currency_usd_id},
        })
        self.check_results(supplier_move_lines, {
            self.account_usd_id: {'debit': 0.0, 'credit': 40.0, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 32.70, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
            self.account_rsa_id: {'debit': 7.30, 'credit': 0.0, 'amount_currency': 0.0, 'currency_id': self.currency_usd_id},
        })

    def test_statement_usd_invoice_chf_transaction_chf(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_swiss_id, self.bank_journal_usd_id, 42, 50, self.currency_swiss_id)
        self.check_results(customer_move_lines, {
            self.account_usd_id: {'debit': 27.47, 'credit': 0.0, 'amount_currency': 42, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 38.21, 'amount_currency': -50, 'currency_id': self.currency_swiss_id},
            self.account_rsa_id: {'debit': 10.74, 'credit': 0.0, 'amount_currency': 0.0, 'currency_id': self.currency_usd_id},
        })
        self.check_results(supplier_move_lines, {
            self.account_usd_id: {'debit': 0.0, 'credit': 27.47, 'amount_currency': -42, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 38.21, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_swiss_id},
            self.account_rsa_id: {'debit': 0.0, 'credit': 10.74, 'amount_currency': 0.0, 'currency_id': self.currency_usd_id},
        })

    def test_statement_eur_invoice_usd_transaction_usd(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_usd_id, self.bank_journal_euro_id, 40, 50, self.currency_usd_id)
        self.check_results(customer_move_lines, {
            self.account_euro_id: {'debit': 40.0, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 32.7, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
            self.account_rsa_id: {'debit': 0.0, 'credit': 7.30, 'amount_currency': 0.0, 'currency_id': False},
        })
        self.check_results(supplier_move_lines, {
            self.account_euro_id: {'debit': 0.0, 'credit': 40.0, 'amount_currency': -50, 'currency_id': self.currency_usd_id},
            self.account_rcv_id: {'debit': 32.7, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_usd_id},
            self.account_rsa_id: {'debit': 7.30, 'credit': 0.0, 'amount_currency': 0.0, 'currency_id': False},
        })

    def test_statement_eur_invoice_usd_transaction_eur(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_usd_id, self.bank_journal_euro_id, 40, 0.0, False)
        self.check_results(customer_move_lines, {
            self.account_euro_id: {'debit': 40.0, 'credit': 0.0, 'amount_currency': 0.0, 'currency_id': False},
            self.account_rcv_id: {'debit': 0.0, 'credit': 40.0, 'amount_currency': -61.16, 'currency_id': self.currency_usd_id},
        })
        self.check_results(supplier_move_lines, {
            self.account_euro_id: {'debit': 0.0, 'credit': 40.0, 'amount_currency': 0.0, 'currency_id': False},
            self.account_rcv_id: {'debit': 40.0, 'credit': 0.0, 'amount_currency': 61.16, 'currency_id': self.currency_usd_id},
        })

    def test_statement_euro_invoice_usd_transaction_chf(self):
        customer_move_lines, supplier_move_lines = self.make_customer_and_supplier_flows(self.currency_usd_id, self.bank_journal_euro_id, 42, 50, self.currency_swiss_id)
        self.check_results(customer_move_lines, {
            self.account_euro_id: {'debit': 42.0, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_swiss_id},
            self.account_rcv_id: {'debit': 0.0, 'credit': 38.21, 'amount_currency': -50, 'currency_id': self.currency_swiss_id},
            self.account_rsa_id: {'debit': 0.0, 'credit': 3.79, 'amount_currency': 0.0, 'currency_id': False},
        })
        self.check_results(supplier_move_lines, {
            self.account_euro_id: {'debit': 0.0, 'credit': 42.0, 'amount_currency': -50, 'currency_id': self.currency_swiss_id},
            self.account_rcv_id: {'debit': 38.21, 'credit': 0.0, 'amount_currency': 50, 'currency_id': self.currency_swiss_id},
            self.account_rsa_id: {'debit': 3.79, 'credit': 0.0, 'amount_currency': 0.0, 'currency_id': False},
        })
