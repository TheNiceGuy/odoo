# -*- coding: utf-'8' "-*-"
from openerp import api, fields, models, _


class PaymentAcquirer(models.Model):
    _name = 'payment.acquirer'
    _inherit = ['payment.acquirer','website.published.mixin']

    is_cod = fields.Boolean()

    @api.model
    def _get_acquirer_buttons(self, order, shipping_partner_id, add_domain=None):
        domain = [('website_published', '=', True), ('company_id', '=', order.company_id.id)]
        if add_domain:
            domain = domain + add_domain
        acquirers = self.search(domain)
        res = list(acquirers)
        acquirer_buttons = acquirers.with_context(submit_class='btn btn-primary', submit_txt=_('Pay Now')).sudo().render(
            '/',
            order.amount_total,
            order.pricelist_id.currency_id.id,
            values={
                'return_url': '/shop/payment/validate',
                'partner_id': shipping_partner_id,
                'billing_partner_id': order.partner_invoice_id.id,
            }
        )
        for index, button in enumerate(acquirer_buttons):
            res[index].button = button
        return res
