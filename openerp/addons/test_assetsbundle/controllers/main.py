# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.http import Controller, request, route
from openerp import SUPERUSER_ID


class TestAssetsBundleController(Controller):
    @route('/test_assetsbundle/js', type='http', auth='user')
    def bundle(self):
        cr, uid, registry, context = request.cr, SUPERUSER_ID, request.registry, request.context
        bundle_id = request.env.ref('test_assetsbundle.bundle1')
        extra_view_ids = registry['ir.ui.view'].search(cr, uid, [('inherit_id', '=', bundle_id.id)])
        context = dict(context, check_view_ids=extra_view_ids)
        return registry['ir.ui.view'].render_template(cr, uid, 'test_assetsbundle.template1', context=context)

    @route('/test_assetsbundle/xml', type='http', auth='user')
    def bundle_xml(self, debug=None):
        cr, uid, registry, context = request.cr, SUPERUSER_ID, request.registry, request.context
        return registry['ir.ui.view'].render(cr, uid, 'test_assetsbundle.template2', context=context)
