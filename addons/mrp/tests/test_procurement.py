# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.mrp.tests.common import TestMrpCommon


class TestProcurement(TestMrpCommon):

    def test_procurement(self):
        """This test case when create production order check procurement is create"""
        # Update BOM
        self.bom_3.bom_line_ids.filtered(lambda x: x.product_id == self.product_5).unlink()
        self.bom_1.bom_line_ids.filtered(lambda x: x.product_id == self.product_1).unlink()

        # Update route
        self.warehouse = self.env.ref('stock.warehouse0')
        route_manufacture = self.warehouse.manufacture_pull_id.route_id.id
        route_mto = self.warehouse.mto_pull_id.route_id.id
        self.product_4.write({'route_ids': [(6, 0, [route_manufacture, route_mto])]})

        # Create production order
        production_2 = self.env['mrp.production'].create({
            'name': 'MO/Test-00002',
            'product_id': self.product_6.id,
            'product_qty': 2.0,
            'bom_id': self.bom_3.id,
            'product_uom_id': self.product_6.uom_id.id,
        })
        production_2.action_assign()

        # check production state is Confirmed
        self.assertEqual(production_2.state, 'confirmed', 'Production order should be for Confirmed state')

        # Check procurement for product 4 created or not.
        procurement = self.env['procurement.order'].search([('group_id', '=', production_2.procurement_group_id.id)])
        self.assertTrue(procurement, 'No procurement are created !')
        self.assertEqual(procurement.state, 'running', 'Procurement order should be in state running')

        # Update Inventory
        inventory_wizard = self.env['stock.change.product.qty'].create({
            'product_id': procurement.production_id.id,
            'new_quantity': 8.0,
        })
        inventory_wizard.change_product_qty()

        procurement.production_id.post_inventory()

        # Check procurement and Production state for product 4.
        procurement.production_id.button_mark_done()
        self.assertEqual(procurement.production_id.state, 'done', 'Production order should be in state done')
        self.assertEqual(procurement.state, 'done', 'Procurement order should be in state done')

        # Update Inventory
        inventory_wizard = self.env['stock.change.product.qty'].create({
            'product_id': production_2.id,
            'new_quantity': 8.0,
        })
        inventory_wizard.change_product_qty()

        production_2.post_inventory()
        # Check procurement and Production state for product 6.
        production_2.button_mark_done()
        self.assertEqual(production_2.state, 'done', 'Production order should be in state done')
