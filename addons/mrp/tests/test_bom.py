# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.mrp.tests.common import TestMrpCommon


class TestBoM(TestMrpCommon):

    def test_basic(self):
        # make the production order
        production = self.production_1

        # # compute production order data
        # production.action_compute()

        # # confirm production
        # production.signal_workflow('button_confirm')
        self.assertEqual(production.state, 'confirmed')

        # reserve product
        # production.force_production()

        # produce product
        produce_wizard = self.env['mrp.product.produce'].with_context({
            'active_id': production.id,
            'active_ids': [production.id],
        }).create({
            'product_qty': 1.0,
        })
        # produce_wizard.on_change_qty()
        produce_wizard.do_produce()

        # check production
        # self.assertEqual(production.state, 'done')

    def test_00_bom_with_phantom(self):
        """ Testing production orders with phantom bom .."""
        Product = self.env['product.product']
        Lot = self.env['stock.production.lot']
        InventoryLine = self.env['stock.inventory.line']
        unit = self.ref("product.product_uom_unit")
        dozen = self.ref("product.product_uom_dozen")

        def create_product(name, uom_id):
            return Product.create({
                'name': name,
                'type': 'product',
                'tracking': 'lot',
                'uom_id': uom_id,
                'uom_po_id': uom_id,
                })

        def create_inventory_line(inventory, product, qty, lot_id=False):
            InventoryLine.create({
                'inventory_id': inventory.id,
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'product_qty': qty,
                'prod_lot_id': lot_id,
                'location_id': self.ref('stock.stock_location_14')})

        product_c = create_product('Product C', unit)
        product_d = create_product('Product D', unit)
        product_e = create_product('Product E', unit)
        product_f = create_product('Product F', unit)

        # Create work center
        #-----------------------

        assembly_workcenter = self.env['mrp.workcenter'].create({
            'name': 'Assembly Station 1',
            'calendar_id' : self.ref('resource.timesheet_group1'),
            })

        # Create routiing
        #-------------------

        assembly_routing = self.env['mrp.routing'].create({
            'name': 'Assembly Line 1',
            'workorder_ids': [
                (0, 0, {'name': 'Machine A', 'workcenter_id': assembly_workcenter.id, 'time_cycle_manual': 20}),
                (0, 0, {'name': 'Machine B', 'workcenter_id': assembly_workcenter.id, 'time_cycle_manual': 10})
            ]})

        # Create bill of material for product E.
        # --------------------------------------

        bom_product_e = self.env['mrp.bom'].create({
            'product_id': product_e.id,
            'product_tmpl_id': product_e.product_tmpl_id.id,
            'product_uom_id': product_e.uom_id.id,
            'product_qty': 4.0,
            'type': 'phantom',
            'bom_line_ids': [
                (0, 0, {'product_id': product_f.id, 'product_qty': 6})
            ]})

        # Create bill of material for product C.
        # --------------------------------------

        bom_product_c = self.env['mrp.bom'].create({
            'product_id': product_c.id,
            'product_tmpl_id': product_c.product_tmpl_id.id,
            'product_uom_id': dozen,
            'product_qty': 2.0,
            'type': 'normal',
            'routing_id': assembly_routing.id,
            'bom_line_ids': [
                (0, 0, {'product_id': product_d.id, 'product_qty': 1}),
                (0, 0, {'product_id': product_e.id, 'product_qty': 2})
            ]})

        # Create production order for product C.
        # --------------------------------------

        mo_product_c = self.env['mrp.production'].create({
            'product_id': product_c.id,
            'product_qty': 48,
            'product_uom_id': unit,
            'bom_id': bom_product_c.id,
            'routing_id': assembly_routing.id})

        # Assign consume material
        # ------------------------

        mo_product_c.action_assign()
        self.assertEqual(mo_product_c.availability, 'waiting', "Production order should be in waiting state.")


        # Check consume material of production order.
        # -------------------------------------------

        move_product_d = mo_product_c.move_raw_ids.filtered(lambda x: x.product_id == product_d)
        move_product_f = mo_product_c.move_raw_ids.filtered(lambda x: x.product_id == product_f)
        self.assertEqual(len(mo_product_c.move_raw_ids), 2, 'Consume material lines are not generated proper.')
        self.assertEqual(move_product_d.product_uom_qty, 2.0, 'Wrong consume quantity of product D.')
        self.assertEqual(move_product_f.product_uom_qty, 6.0, 'Wrong consume quantity of product F.')

        # Create Lots for Product D and Product F
        # ---------------------------------------

        lot_product_d = Lot.create({'product_id': product_d.id})
        lot_product_f = Lot.create({'product_id': product_f.id})

        # Create Inventory for consume material product D and F.
        # ------------------------------------------------------

        inventory = self.env['stock.inventory'].create({
            'name': 'Inventory For Product C',
            'filter': 'partial'})
        inventory.prepare_inventory()

        self.assertFalse(inventory.line_ids, "Inventory line should not created.")
        create_inventory_line(inventory, product_d, 2, lot_product_d.id)
        create_inventory_line(inventory, product_f, 6, lot_product_f.id)
        inventory.action_done()

        # Assign consume material
        # ------------------------
        mo_product_c.action_assign()

        # Check production order status after assign.
        self.assertEqual(mo_product_c.availability, 'assigned', "Production order should be in assigned state.")
        # Plan production order.
        mo_product_c.button_plan()


        # ---------------------------------------------
        # Check workorder process of production order.
        # ---------------------------------------------

        workorders = mo_product_c.workorder_ids
        # Check machine A process....
        self.assertEqual(workorders[0].duration, 40, "Workorder duration does not match.")
        workorders[0].button_start()
        finished_lot = Lot.create({'product_id': mo_product_c.product_id.id})
        workorders[0].write({'final_lot_id': finished_lot.id, 'qty_producing': 48})
        product_d_move_lot = workorders[1].active_move_lot_ids.filtered(lambda x: x.product_id.id == product_d.id)
        product_d_move_lot.write({'lot_id': lot_product_d.id, 'quantity_done': 2})
        workorders[0].record_production()

        # Check machine B process....
        self.assertEqual(workorders[1].duration, 20, "Workorder duration does not match.")
        workorders[1].button_start()
        product_f_move_lot = workorders[1].active_move_lot_ids.filtered(lambda x: x.product_id.id == product_f.id)
        product_f_move_lot.write({'lot_id': lot_product_f.id, 'quantity_done': 6})
        workorders[1].record_production()
        mo_product_c.button_mark_done()
