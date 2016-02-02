# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Copyright (c) 2010 Camptocamp SA (http://www.camptocamp.com)
# Author : Nicolas Bessi (Camptocamp)


from odoo.addons.report_webkit.models.webkit_report import webkit_report_extender
from odoo import SUPERUSER_ID

@webkit_report_extender("report_webkit.webkit_demo_report")
def extend_demo(pool, cr, uid, localcontext, context):
    admin = pool.get("res.users").browse(cr, uid, SUPERUSER_ID, context)
    localcontext.update({
        "admin_name": admin.name,
    })
