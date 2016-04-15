# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import odoo.tests

@openerp.tests.common.at_install(False)
@openerp.tests.common.post_install(True)
class TestUi(openerp.tests.HttpCase):
    def test_admin(self):
        self.phantom_js("/", "odoo.__DEBUG__.services['web.Tour'].run('blog', 'test')", "odoo.__DEBUG__.services['web.Tour'].tours.blog", login='admin')
