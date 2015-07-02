# -*- coding: utf-8 -*-
import logging

from openerp import _, api, fields, models
from openerp.tools import float_round, float_repr

_logger = logging.getLogger(__name__)


def _partner_format_address(address1=False, address2=False):
    return ' '.join((address1 or '', address2 or '')).strip()


def _partner_split_name(partner_name):
    return [' '.join(partner_name.split()[-1:]), ' '.join(partner_name.split()[:-1])]


class ValidationError(ValueError):

    """ Used for value error when validating transaction data coming from acquirers. """
    pass


class PaymentAcquirer(models.Model):

    """ Acquirer Model. Each specific acquirer can extend the model by adding
    its own fields, using the acquirer_name as a prefix for the new fields.
    Using the required_if_provider='<name>' attribute on fields it is possible
    to have required fields that depend on a specific acquirer.

    Each acquirer has a link to an ir.ui.view record that is a template of
    a button used to display the payment form. See examples in ``payment_ogone``
    and ``payment_paypal`` modules.

    Methods that should be added in an acquirer-specific implementation:

     - ``<name>_form_generate_values(self, cr, uid, id, reference, amount, currency,
       partner_id=False, partner_values=None, tx_custom_values=None, context=None)``:
       method that generates the values used to render the form button template.
     - ``<name>_get_form_action_url(self, cr, uid, id, context=None):``: method
       that returns the url of the button form. It is used for example in
       ecommerce application, if you want to post some data to the acquirer.
     - ``<name>_compute_fees(self, cr, uid, id, amount, currency_id, country_id,
       context=None)``: computed the fees of the acquirer, using generic fields
       defined on the acquirer model (see fields definition).

    Each acquirer should also define controllers to handle communication between
    OpenERP and the acquirer. It generally consists in return urls given to the
    button form and that the acquirer uses to send the customer back after the
    transaction, with transaction details given as a POST request.
    """
    _name = 'payment.acquirer'
    _description = 'Payment Acquirer'
    _order = 'sequence'

    @api.model
    def _get_providers(self):
        return []

    # indirection to ease inheritance
    _provider_selection = lambda self, *args, **kwargs: self._get_providers(*args, **kwargs)

    name = fields.Char(required=True, translate=True)
    provider = fields.Selection(_provider_selection, required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.user.company_id.id)
    pre_msg = fields.Html(string='Message', translate=True,
                          help='Message displayed to explain and help the payment process.')
    post_msg = fields.Html(string='Thanks Message', help='Message displayed after having done the payment process.')
    validation = fields.Selection(
        [('manual', 'Manual'), ('automatic', 'Automatic')],
        string='Process Method',
        help='Static payments are payments like transfer, that require manual steps.', default='automatic')
    view_template_id = fields.Many2one('ir.ui.view', string='Form Button Template', required=True)
    registration_view_template_id = fields.Many2one('ir.ui.view', string='S2S Form Template',
                                                    domain=[('type', '=', 'qweb')],
                                                    help="Template for method registration")
    environment = fields.Selection(
        [('test', 'Test'), ('prod', 'Production')],
        string='Environment', oldname='env', default='test')
    website_published = fields.Boolean(
        string='Visible in Portal / Website', copy=False,
        help="Make this payment acquirer available (Customer invoices, etc.)", default=True)
    auto_confirm = fields.Selection(
        [('none', 'No automatic confirmation'),
         ('at_pay_confirm', 'At payment confirmation'),
         ('at_pay_now', 'At payment')],
        string='Order Confirmation', required=True, default='at_pay_confirm')
    pending_msg = fields.Html(string='Pending Message', translate=True, help='Message displayed, if order is in pending state after having done the payment process.', default='<i>Pending,</i> Your online payment has been successfully processed. But your order is not validated yet.')
    done_msg = fields.Html(string='Done Message', translate=True, help='Message displayed, if order is done successfully after having done the payment process.', default='<i>Done,</i> Your online payment has been successfully processed. Thank you for your order.')
    cancel_msg = fields.Html(string='Cancel Message', translate=True, help='Message displayed, if order is cancel during the payment process.', default='<i>Cancel,</i> Your payment has been cancelled.')
    error_msg = fields.Html(string='Error Message', translate=True, help='Message displayed, if error is occur during the payment process.', default='<i>Error,</i> An error occurred. We cannot process your payment for the moment, please try again later.')
    # Fees
    fees_active = fields.Boolean(string='Compute fees')
    fees_dom_fixed = fields.Float(string='Fixed domestic fees')
    fees_dom_var = fields.Float(string='Variable domestic fees (in percents)')
    fees_int_fixed = fields.Float(string='Fixed international fees')
    fees_int_var = fields.Float(string='Variable international fees (in percents)')
    sequence = fields.Integer(help="Determine the display order")

    @api.multi
    @api.constrains('provider')
    def _check_required_if_provider(self):
        """ If the field has 'required_if_provider="<provider>"' attribute, then it
        required if record.provider is <provider>. """
        for acquirer in self:
            if any(getattr(f, 'required_if_provider', None) == acquirer.provider and not acquirer[k] for k, f in self._fields.items()):
                raise ValidationError('Required fields not filled, [required for this provider]')
        return True

    @api.multi
    def get_form_action_url(self):
        """ Returns the form action URL, for form-based acquirer implementations. """
        if hasattr(self, '%s_get_form_action_url' % self.provider):
            return ''.join(getattr(self, '%s_get_form_action_url' % self.provider)())
        return False

    @api.multi
    def form_preprocess_values(self, reference, amount, currency_id, tx_id, partner_id, partner_values, tx_values):
        self.ensure_one()
        """  Pre process values before giving them to the acquirer-specific render
        methods. Those methods will receive:

             - partner_values: will contain name, lang, email, zip, address, city,
               country_id (int or False), country (browse or False), phone, reference
             - tx_values: will contain reference, amount, currency_id (int or False),
               currency (browse or False), partner (browse or False)
        """

        if tx_id:
            tx = self.env['payment.transaction'].browse(tx_id)
            tx_data = {
                'reference': tx.reference,
                'amount': tx.amount,
                'currency_id': tx.currency_id.id,
                'currency': tx.currency_id,
                'partner': tx.partner_id,
            }
            partner_data = {
                'name': tx.partner_name,
                'lang': tx.partner_lang,
                'email': tx.partner_email,
                'zip': tx.partner_zip,
                'address': tx.partner_address,
                'city': tx.partner_city,
                'country_id': tx.partner_country_id.id,
                'country': tx.partner_country_id,
                'phone': tx.partner_phone,
                'reference': tx.partner_reference,
                'state': None,
            }
        else:
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                partner_data = {
                    'name': partner.name,
                    'lang': partner.lang,
                    'email': partner.email,
                    'zip': partner.zip,
                    'city': partner.city,
                    'address': _partner_format_address(partner.street, partner.street2),
                    'country_id': partner.country_id.id,
                    'country': partner.country_id,
                    'phone': partner.phone,
                    'state': partner.state_id,
                }
            else:
                partner, partner_data = False, {}
            partner_data.update(partner_values)

            if currency_id:
                currency = self.env['res.currency'].browse(currency_id)
            else:
                currency = self.env.user.company_id.currency_id
            tx_data = {
                'reference': reference,
                'amount': amount,
                'currency_id': currency.id,
                'currency': currency,
                'partner': partner,
            }

        # update tx values
        tx_data.update(tx_values)

        # update partner values
        if not partner_data.get('address'):
            partner_data['address'] = _partner_format_address(partner_data.get('street', ''), partner_data.get('street2', ''))
        if not partner_data.get('country') and partner_data.get('country_id'):
            partner_data['country'] = self.env['res.country'].browse(partner_data.get('country_id'))
        partner_data.update({
            'first_name': _partner_split_name(partner_data['name'])[0],
            'last_name': _partner_split_name(partner_data['name'])[1],
        })

        # compute fees
        fees_method_name = '%s_compute_fees' % self.provider
        if hasattr(self, fees_method_name):
            fees = getattr(self, fees_method_name)(
                tx_data['amount'], tx_data['currency_id'], partner_data['country_id'])
            tx_data['fees'] = float_round(fees[0], 2)

        return (partner_data, tx_data)

    @api.multi
    def render(self, reference, amount, currency_id, tx_id=None, partner_id=False, partner_values=None, tx_values=None):
        self.ensure_one()
        """ Renders the form template of the given acquirer as a qWeb template.
        All templates will receive:

         - acquirer: the payment.acquirer browse record
         - user: the current user browse record
         - currency_id: id of the transaction currency
         - amount: amount of the transaction
         - reference: reference of the transaction
         - partner: the current partner browse record, if any (not necessarily set)
         - partner_values: a dictionary of partner-related values
         - tx_values: a dictionary of transaction related values that depends on
                      the acquirer. Some specific keys should be managed in each
                      provider, depending on the features it offers:

          - 'feedback_url': feedback URL, controler that manage answer of the acquirer
                            (without base url) -> FIXME
          - 'return_url': URL for coming back after payment validation (wihout
                          base url) -> FIXME
          - 'cancel_url': URL if the client cancels the payment -> FIXME
          - 'error_url': URL if there is an issue with the payment -> FIXME

         - context: OpenERP context dictionary

        :param string reference: the transaction reference
        :param float amount: the amount the buyer has to pay
        :param res.currency browse record currency: currency
        :param int tx_id: id of a transaction; if set, bypasses all other given
                          values and only render the already-stored transaction
        :param res.partner browse record partner_id: the buyer
        :param dict partner_values: a dictionary of values for the buyer (see above)
        :param dict tx_custom_values: a dictionary of values for the transction
                                      that is given to the acquirer-specific method
                                      generating the form values
        :param dict context: OpenERP context
        """
        if tx_values is None:
            tx_values = {}
        if partner_values is None:
            partner_values = {}

        # pre-process values
        amount = float_round(amount, 2)
        partner_values, tx_values = self.form_preprocess_values(
            reference, amount, currency_id, tx_id, partner_id,
            partner_values, tx_values)

        # call <name>_form_generate_values to update the tx dict with acqurier specific values
        cust_method_name = '%s_form_generate_values' % (self.provider)
        if hasattr(self, cust_method_name):
            method = getattr(self, cust_method_name)
            inv_type = method(partner_values, tx_values)
            partner_values, tx_values = inv_type[0] if isinstance(inv_type, list) else inv_type

        qweb_context = {
            'tx_url': self.get_form_action_url(),
            'submit_class': self.env.context.get('submit_class', 'btn btn-link'),
            'submit_txt': self.env.context.get('submit_txt'),
            'acquirer': self,
            'user': self.env.user,
            'reference': tx_values['reference'],
            'amount': tx_values['amount'],
            'currency': tx_values['currency'],
            'partner': tx_values.get('partner'),
            'partner_values': partner_values,
            'tx_values': tx_values,
            'context': self.env.context,
            'type': tx_values.get('type') or 'form',
        }

        # because render accepts view ids but not qweb -> need to use the xml_id
        return self.pool['ir.ui.view'].render(self._cr, self._uid, self.view_template_id.xml_id, qweb_context, engine='ir.qweb', context=self.env.context)

    @api.one
    def _registration_render(self, partner_id, qweb_context=None):
        if qweb_context is None:
            qweb_context = {}
        qweb_context.update(id=id, partner_id=partner_id)
        method_name = '_%s_registration_form_generate_values' % (self.provider,)
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            qweb_context.update(method(qweb_context))
        return self.pool['ir.ui.view'].render(self._cr, self._uid, self.registration_view_template_id.xml_id, qweb_context, engine='ir.qweb', context=self.env.context)

    @api.one
    def s2s_process(self, data):
        cust_method_name = '%s_s2s_form_process' % (self.provider)
        if not self.s2s_validate(data):
            return False
        if hasattr(self, cust_method_name):
            method = getattr(self, cust_method_name)
            return method(data)
        return True

    @api.one
    def s2s_validate(self, data):
        cust_method_name = '%s_s2s_form_validate' % (self.provider)
        if hasattr(self, cust_method_name):
            method = getattr(self, cust_method_name)
            return method(data)
        return True

    @api.model
    def _wrap_payment_block(self, html_block, amount, currency_id):
        payment_header = _('Pay safely online')
        currency = self.env['res.currency'].browse(currency_id)
        amount_str = float_repr(amount, currency.decimal_places)
        currency_str = currency.symbol or currency.name
        amount = u"%s %s" % ((currency_str, amount_str) if currency.position == 'before' else (amount_str, currency_str))
        result = u"""<div class="payment_acquirers">
                         <div class="payment_header">
                             <div class="payment_amount">%s</div>
                             %s
                         </div>
                         %%s
                     </div>""" % (amount, payment_header)
        return result % html_block.decode("utf-8")

    @api.model
    def render_payment_block(self, reference, amount, currency_id, tx_id=None, partner_id=False, partner_values=None, tx_values=None, company_id=None):
        html_forms = []
        domain = [('website_published', '=', True), ('validation', '=', 'automatic')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        acquirers = self.search(domain)
        for acquirer in acquirers:
            button = acquirer.render(
                reference, amount, currency_id,
                tx_id, partner_id, partner_values, tx_values)
            html_forms.append(button)
        if not html_forms:
            return ''
        html_block = '\n'.join(filter(None, html_forms))
        return self._wrap_payment_block(html_block, amount, currency_id)


class PaymentTransaction(models.Model):

    """ Transaction Model. Each specific acquirer can extend the model by adding
    its own fields.

    Methods that can be added in an acquirer-specific implementation:

     - ``<name>_create``: method receiving values used when creating a new
       transaction and that returns a dictionary that will update those values.
       This method can be used to tweak some transaction values.

    Methods defined for convention, depending on your controllers:

     - ``<name>_form_feedback(self, cr, uid, data, context=None)``: method that
       handles the data coming from the acquirer after the transaction. It will
       generally receives data posted by the acquirer after the transaction.
    """
    _name = 'payment.transaction'
    _description = 'Payment Transaction'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _rec_name = 'reference'

    date_create = fields.Datetime(string='Creation Date', readonly=True, required=True, default=fields.Datetime.now)
    date_validate = fields.Datetime(string='Validation Date')
    acquirer_id = fields.Many2one('payment.acquirer', string='Acquirer', required=True)
    type = fields.Selection(
        [('server2server', 'Server To Server'), ('form', 'Form'), ('form_save', 'Form with credentials storage')],
        string='Type', required=True, default='form')
    state = fields.Selection(
        [('draft', 'Draft'), ('pending', 'Pending'),
         ('done', 'Done'), ('error', 'Error'),
         ('cancel', 'Canceled')
         ], string='Status', required=True,
        track_visiblity='onchange', copy=False, default='draft')
    state_message = fields.Text(string='Message',
                                help='Field used to store error and/or validation messages for information')
    # payment
    amount = fields.Float(required=True,
                          digits=(16, 2),
                          track_visibility='always',
                          help='Amount in cents')
    fees = fields.Float(digits=(16, 2),
                        track_visibility='always',
                        help='Fees amount; set by the system because depends on the acquirer')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    reference = fields.Char(string='Order Reference', required=True)
    acquirer_reference = fields.Char(string='Acquirer Order Reference',
                                     help='Reference of the TX as stored in the acquirer database')
    # duplicate partner / transaction data to store the values at transaction time
    partner_id = fields.Many2one('res.partner', string='Partner', track_visibility='onchange',)
    partner_name = fields.Char(string='Partner Name')
    partner_lang = fields.Char(string='Lang', default='en_US')
    partner_email = fields.Char(string='Email')
    partner_zip = fields.Char(string='Zip')
    partner_address = fields.Char(string='Address')
    partner_city = fields.Char(string='City')
    partner_country_id = fields.Many2one('res.country', string='Country', required=True)
    partner_phone = fields.Char(string='Phone')
    partner_reference = fields.Char(string='Partner Reference',
                                    help='Reference of the customer in the acquirer database')
    html_3ds = fields.Char(string='3D Secure HTML')

    s2s_cb_eval = fields.Char(string='S2S Callback', help="""\
        Will be safe_eval with `self` being the current transaction. i.e.:
            self.env['my.model'].payment_validated(self)""")

    @api.one
    @api.constrains('reference', 'state')
    def _check_reference(self):
        if self.state not in ['cancel', 'error']:
            if self.search_count([('reference', '=', self.reference), ('id', '!=', self.id)]):
                raise ValidationError(_('The payment transaction reference must be unique!'))
        return True

    @api.model
    def create(self, values):
        Acquirer = self.env['payment.acquirer']
        if values.get('partner_id'):  # @TDENOTE: not sure
            values.update(self.on_change_partner_id(values.get('partner_id'))['values'])

        # call custom create method if defined (i.e. ogone_create for ogone)
        if values.get('acquirer_id'):
            acquirer = self.env['payment.acquirer'].browse(values.get('acquirer_id'))

            # compute fees
            custom_method_name = '%s_compute_fees' % acquirer.provider
            if hasattr(Acquirer, custom_method_name):
                fees = getattr(acquirer, custom_method_name)(
                    values.get('amount', 0.0), values.get('currency_id'), values.get('country_id'))
                values['fees'] = float_round(fees[0], 2)

            # custom create
            custom_method_name = '%s_create' % acquirer.provider
            if hasattr(self, custom_method_name):
                values.update(getattr(self, custom_method_name)(values))

        return super(PaymentTransaction, self).create(values)

    @api.multi
    def on_change_partner_id(self, partner_id):
        partner = None
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
        return {'values': {
            'partner_name': partner and partner.name or False,
            'partner_lang': partner and partner.lang or 'en_US',
            'partner_email': partner and partner.email or False,
            'partner_zip': partner and partner.zip or False,
            'partner_address': _partner_format_address(partner and partner.street or '', partner and partner.street2 or ''),
            'partner_city': partner and partner.city or False,
            'partner_country_id': partner and partner.country_id.id or False,
            'partner_phone': partner and partner.phone or False,
        }}

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def form_feedback(self, data, acquirer_name):
        invalid_parameters, tx = None, None

        tx_find_method_name = '_%s_form_get_tx_from_data' % acquirer_name
        if hasattr(self, tx_find_method_name):
            tx = getattr(self, tx_find_method_name)(data)

        invalid_param_method_name = '_%s_form_get_invalid_parameters' % acquirer_name
        if hasattr(self, invalid_param_method_name):
            invalid_parameters = getattr(self, invalid_param_method_name)(tx, data)

        if invalid_parameters:
            _error_message = '%s: incorrect tx data:\n' % (acquirer_name)
            for item in invalid_parameters:
                _error_message += '\t%s: received %s instead of %s\n' % (item[0], item[1], item[2])
            _logger.error(_error_message)
            return False

        feedback_method_name = '_%s_form_validate' % acquirer_name
        if hasattr(self, feedback_method_name):
            return getattr(self, feedback_method_name)(tx, data)

        return True

    # --------------------------------------------------
    # SERVER2SERVER RELATED METHODS
    # --------------------------------------------------
    @api.model
    def s2s_create(self, values, cc_values):
        tx_id, tx_result = self.s2s_send(values, cc_values)
        self.s2s_feedback(tx_id, tx_result)
        return tx_id

    @api.one
    def s2s_do_transaction(self, **kwargs):
        custom_method_name = '%s_s2s_do_transaction' % self.acquirer_id.provider
        if hasattr(self, custom_method_name):
            return getattr(self, custom_method_name)(**kwargs)

    @api.model
    def s2s_get_tx_status(self, tx_id):
        """ Get the tx status. """
        tx = self.browse(tx_id)

        invalid_param_method_name = '_%s_s2s_get_tx_status' % tx.acquirer_id.provider
        if hasattr(self, invalid_param_method_name):
            return getattr(self, invalid_param_method_name)(tx)

        return True


class PaymentMethod(models.Model):
    _name = 'payment.method'
    _order = 'partner_id'

    name = fields.Char(help='Name of the payment method')
    partner_id = fields.Many2one('res.partner', string='Partner', required=True)
    acquirer_id = fields.Many2one('payment.acquirer', string='Acquirer Account', required=True)
    acquirer_ref = fields.Char(string='Acquirer Ref.', required=True)
    active = fields.Boolean(default=True)

    @api.model
    def create(self, values):
        # call custom create method if defined (i.e. ogone_create for ogone)
        if values.get('acquirer_id'):
            acquirer = self.env['payment.acquirer'].browse(values.get('acquirer_id'))

            # custom create
            custom_method_name = '%s_create' % acquirer.provider
            if hasattr(self, custom_method_name):
                values.update(getattr(self, custom_method_name)(values))

        return super(PaymentMethod, self).create(values)
