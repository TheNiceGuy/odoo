# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from openerp.tools.translate import _

from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round
from openerp import SUPERUSER_ID
from dateutil.relativedelta import relativedelta
from datetime import datetime
from psycopg2 import OperationalError
import openerp


class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    partner_id = fields.Many2one('res.partner', string='Partner')


class ProcurementRule(models.Model):
    _inherit = 'procurement.rule'

    @api.model
    def _get_action(self):
        result = super(ProcurementRule, self)._get_action()
        return result + [('move', _('Move From Another Location'))]

    location_id = fields.Many2one('stock.location', string='Procurement Location')
    location_src_id = fields.Many2one('stock.location', string='Source Location', help="Source location is action=move")
    route_id = fields.Many2one('stock.location.route', string='Route', help="If route_id is False, the rule is global")
    procure_method = fields.Selection([('make_to_stock', 'Take From Stock'), ('make_to_order', 'Create Procurement')], string='Move Supply Method', required=True, help="""Determines the procurement method of the stock move that will be generated: whether it will need to 'take from the available stock' in its source location or needs to ignore its stock and create a procurement over there.""", default='make_to_stock')
    route_sequence = fields.Integer(related='route_id.sequence', string='Route Sequence', store=True)
    picking_type_id = fields.Many2one('stock.picking.type', string='Picking Type', help="Picking Type determines the way the picking should be shown in the view, reports, ...")
    delay = fields.Integer(string='Number of Days', default=0)
    partner_address_id = fields.Many2one('res.partner', string='Partner Address')
    propagate = fields.Boolean(string='Propagate cancel and split', default=True, help='If checked, when the previous move of the move (which was generated by a next procurement) is cancelled or split, the move generated by this move will too')
    warehouse_id = fields.Many2one('stock.warehouse', string='Served Warehouse', help='The warehouse this rule is for')
    propagate_warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse to Propagate', help="The warehouse to propagate on the created move/procurement, which can be different of the warehouse this rule is for (e.g for resupplying rules from another warehouse)")


class ProcurementOrder(models.Model):
    _inherit = "procurement.order"

    location_id = fields.Many2one('stock.location', string='Procurement Location')  # not required because task may create procurements that aren't linked to a location with sale_service
    partner_dest_id = fields.Many2one('res.partner', string='Customer Address', help="In case of dropshipping, we need to know the destination address more precisely")
    move_ids = fields.One2many('stock.move', 'procurement_id', string='Moves', help="Moves created by the procurement")
    move_dest_id = fields.Many2one('stock.move', string='Destination Move', help="Move which caused (created) the procurement")
    route_ids = fields.Many2many('stock.location.route', 'stock_location_route_procurement', 'procurement_id', 'route_id', string='Preferred Routes', help="Preferred route to be followed by the procurement order. Usually copied from the generating document (SO) but could be set up manually.")
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', help="Warehouse to consider for the route selection")
    orderpoint_id = fields.Many2one('stock.warehouse.orderpoint', string='Minimum Stock Rule')

    @api.multi
    def propagate_cancels(self):
        self.filtered(lambda proc: proc.rule_id.action == 'move' and proc.move_ids).mapped('move_ids').action_cancel()
        return True

    @api.multi
    def cancel(self):
        self.browse(self.get_cancel_ids()).with_context(cancel_procurement=True).propagate_cancels()
        return super(ProcurementOrder, self).cancel()

    @api.model
    def _find_parent_locations(self, procurement):
        location = procurement.location_id
        res = [location.id]
        while location.location_id:
            location = location.location_id
            res.append(location.location_id.id)
        return res

    @api.onchange('warehouse_id')
    def change_warehouse_id(self):
        if self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id.id

    #Doing assignation, ... in multi
    @api.model
    def _assign_multi(self, procurements):
        res = {}
        todo_procs = []
        for procurement in procurements:
            if procurement.rule_id:
                res[procurement.id] = True
            elif procurement.product_id.type in ['product', 'consu']:
                todo_procs += [procurement.id]
        procs = self.browse(todo_procs)
        res_dict = procs._find_suitable_rule_multi()
        rule_dict = {}
        for proc in res_dict.keys():
            if res_dict[proc]:
                if rule_dict.get(res_dict[proc]):
                    rule_dict[res_dict[proc]] += [proc]
                else:
                    rule_dict[res_dict[proc]] = [proc]
        for rule in rule_dict.keys():
            procs = self.browse(rule_dict[rule])
            procs.write({'rule_id': rule})

    @api.multi
    def _get_route_group_dict(self):
        """
            Returns a dictionary with key the routes and values the products associated
        """
        self.env.cr.execute("""
            SELECT proc_id, route_id FROM
            ((SELECT p.id AS proc_id, route_id
                FROM stock_route_product AS link, procurement_order AS p, product_template AS pt, product_product pp
                WHERE pp.product_tmpl_id = pt.id AND link.product_id = pt.id AND pp.id = p.product_id
                    AND p.id in %s)
             UNION (SELECT p.id AS proc_id, link.route_id AS route_id
                    FROM stock_location_route_categ AS link, product_product AS pp, procurement_order AS p,
                         product_template AS pt, product_category AS pc, product_category AS pc_product
                    WHERE p.product_id = pp.id AND pp.product_tmpl_id = pt.id AND pc_product.id = pt.categ_id AND
                    pc.parent_left <= pc_product.parent_left AND pc.parent_right >= pc_product.parent_left
                    AND link.categ_id = pc.id AND pp.id IN %s)) p ORDER BY proc_id, route_id
        """, (tuple(self.ids), tuple(self.ids), ))
        product_routes = self.env.cr.fetchall()
        old_proc = False
        key = tuple()
        key_routes = {}
        for proc, route in product_routes:
            key += (route,)
            if old_proc != proc:
                if key:
                    if key_routes.get(key):
                        key_routes[key] += [proc]
                    else:
                        key_routes[key] = [proc]
                old_proc = proc
                key = tuple()
        return key_routes

    @api.multi
    def _get_wh_loc_dict(self):
        wh_dict = {}
        for procurement in self:
            if wh_dict.get(procurement.warehouse_id.id):
                if wh_dict[procurement.warehouse_id.id].get(procurement.location_id):
                    wh_dict[procurement.warehouse_id.id][procurement.location_id] += procurement
                else:
                    wh_dict[procurement.warehouse_id.id][procurement.location_id] = procurement
            else:
                wh_dict[procurement.warehouse_id.id] = {}
                wh_dict[procurement.warehouse_id.id][procurement.location_id] = procurement
        return wh_dict

    @api.multi
    def _find_suitable_rule_multi(self, domain=[]):
        '''we try to first find a rule among the ones defined on the procurement order group and if none is found, we try on the routes defined for the product, and finally we fallback on the default behavior'''
        results_dict = {}
        Rule = self.env['procurement.rule']
        warehouse_route_ids = []
        for procurement in self:  # Could be replaced by one query for all route_ids
            if procurement.route_ids:
                loc = procurement.location_id
                loc_domain = [('location_id.parent_left', '<=', loc.parent_left),
                                ('location_id.parent_right', '>=', loc.parent_left)]
                if procurement.warehouse_id:
                    domain += ['|', ('warehouse_id', '=', procurement.warehouse_id.id), ('warehouse_id', '=', False)]
                rule = Rule.search(loc_domain + [('route_id', 'in', procurement.route_ids.ids)], order='route_sequence, sequence', limit=1)
                results_dict[procurement.id] = rule.id
        procurements_to_check = self.filtered(lambda x: x.id not in results_dict.keys())
        # group by warehouse_id:
        wh_dict = procurements_to_check._get_wh_loc_dict()
        for wh in wh_dict.keys():
            warehouse_route_ids = []
            domain = []
            check_wh = False
            for loc in wh_dict[wh].keys():
                procurement = wh_dict[wh][loc][0]
                loc_domain = [('location_id.parent_left', '<=', loc.parent_left),
                                ('location_id.parent_right', '>=', loc.parent_left)]
                if wh and not check_wh:
                    domain += ['|', ('warehouse_id', '=', procurement.warehouse_id.id), ('warehouse_id', '=', False)]
                    warehouse_route_ids = procurement.warehouse_id.route_ids.ids
                check_wh = True
                key_routes = wh_dict[wh][loc]._get_route_group_dict()
                for key in key_routes.keys():
                    domain = loc_domain + domain
                    rule = Rule.search(domain + [('route_id', 'in', list(key))], order='route_sequence, sequence', limit=1)
                    result = False
                    if rule:
                        result = rule.id
                    elif warehouse_route_ids:
                        rule = Rule.search(domain + [('route_id', 'in', warehouse_route_ids)], order='route_sequence, sequence', limit=1)
                        result = rule.id
                    if not result:
                        rule = Rule.search(domain + [('route_id', '=', False)], order='sequence', limit=1)
                        result = rule.id
                    for proc in key_routes[key]:
                        results_dict[proc] = result
        return results_dict

    @api.multi
    def _search_suitable_rule(self, domain):
        '''we try to first find a rule among the ones defined on the procurement order group and if none is found, we try on the routes defined for the product, and finally we fallback on the default behavior'''
        Rule = self.env['procurement.rule']
        self.ensure_one()
        warehouse_route_ids = []
        if self.warehouse_id:
            domain += ['|', ('warehouse_id', '=', self.warehouse_id.id), ('warehouse_id', '=', False)]
            warehouse_route_ids = self.warehouse_id.route_ids.ids
        product_route_ids = self.product_id.route_ids.ids + self.product_id.categ_id.total_route_ids.ids
        procurement_route_ids = self.route_ids.ids
        procurement_rules = Rule.search(domain + [('route_id', 'in', procurement_route_ids)], order='route_sequence, sequence')
        if not procurement_rules:
            procurement_rules = Rule.search(domain + [('route_id', 'in', product_route_ids)], order='route_sequence, sequence')
            if not procurement_rules:
                procurement_rules = warehouse_route_ids and Rule.search(domain + [('route_id', 'in', warehouse_route_ids)], order='route_sequence, sequence') or []
                if not procurement_rules:
                    procurement_rules = Rule.search(domain + [('route_id', '=', False)], order='sequence')
        return procurement_rules.ids

    @api.model
    def _find_suitable_rule(self, procurement):
        rule_id = super(ProcurementOrder, self)._find_suitable_rule(procurement)
        if not rule_id:
            # a rule defined on 'Stock' is suitable for a procurement in 'Stock\Bin A'
            all_parent_location_ids = self._find_parent_locations(procurement)
            rule_ids = procurement._search_suitable_rule([('location_id', 'in', all_parent_location_ids)])
            rule_id = rule_ids and rule_ids[0] or False
        return rule_id

    @api.model
    def _run_move_create(self, procurement):
        ''' Returns a dictionary of values that will be used to create a stock move from a procurement.
        This function assumes that the given procurement has a rule (action == 'move') set on it.
        :param procurement: browse record
        :rtype: dictionary
        '''
        newdate = (datetime.strptime(procurement.date_planned, '%Y-%m-%d %H:%M:%S') - relativedelta(days=procurement.rule_id.delay or 0)).strftime('%Y-%m-%d %H:%M:%S')
        group_id = False
        if procurement.rule_id.group_propagation_option == 'propagate':
            group_id = procurement.group_id.id
        elif procurement.rule_id.group_propagation_option == 'fixed':
            group_id = procurement.rule_id.group_id.id
        # it is possible that we've already got some move done, so check for the done qty and create
        # a new move with the correct qty
        already_done_qty = 0
        already_done_qty_uos = 0
        for move in procurement.move_ids:
            already_done_qty += move.product_uom_qty if move.state == 'done' else 0
            already_done_qty_uos += move.product_uos_qty if move.state == 'done' else 0
        qty_left = max(procurement.product_qty - already_done_qty, 0)
        vals = {
            'name': procurement.name,
            'company_id': procurement.rule_id.company_id.id or procurement.rule_id.location_src_id.company_id.id or procurement.rule_id.location_id.company_id.id or procurement.company_id.id,
            'product_id': procurement.product_id.id,
            'product_uom': procurement.product_uom.id,
            'product_uom_qty': qty_left,
            'partner_id': procurement.rule_id.partner_address_id.id or procurement.group_id.partner_id.id or False,
            'location_id': procurement.rule_id.location_src_id.id,
            'location_dest_id': procurement.location_id.id,
            'move_dest_id': procurement.move_dest_id.id,
            'procurement_id': procurement.id,
            'rule_id': procurement.rule_id.id,
            'procure_method': procurement.rule_id.procure_method,
            'origin': procurement.origin,
            'picking_type_id': procurement.rule_id.picking_type_id.id,
            'group_id': group_id,
            'route_ids': [(4, x.id) for x in procurement.route_ids],
            'warehouse_id': procurement.rule_id.propagate_warehouse_id.id or procurement.rule_id.warehouse_id.id,
            'date': newdate,
            'date_expected': newdate,
            'propagate': procurement.rule_id.propagate,
            'priority': procurement.priority,
        }
        return vals

    @api.model
    def _run(self, procurement):
        StockMove = self.env['stock.move']
        if procurement.rule_id.action == 'move':
            if not procurement.rule_id.location_src_id:
                procurement.message_post(body=_('No source location defined!'))
                return False
            move_dict = self._run_move_create(procurement)
            # create the move as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
            StockMove.sudo().create(move_dict)
            return True
        return super(ProcurementOrder, self)._run(procurement)

    @api.multi
    def run(self, autocommit=False):
        new_ids = self.filtered(lambda self: self.state not in ('running', 'done', 'cancel'))
        # new_ids = [x.id for x in self.ids if x.state not in ('running', 'done', 'cancel')]
        # res = super(ProcurementOrder, self._model).run(autocommit=autocommit)
        res = super(ProcurementOrder, self._model).run(self._cr, self._uid, new_ids.ids, autocommit=autocommit, context=self._context)

        # after all the procurements are run, check if some created a draft stock move that needs to be confirmed
        # (we do that in batch because it fasts the picking assignation and the picking state computation)
        move_to_confirm_ids = []
        for procurement in new_ids:
            if procurement.state == "running" and procurement.rule_id and procurement.rule_id.action == "move":
                # move_to_confirm_ids += [m.id for m in procurement.move_ids if m.state == 'draft']
                move_to_confirm_ids.append(procurement.move_ids.filtered(lambda m: m.state == 'draft'))
        if move_to_confirm_ids:
            move_to_confirm_ids[0]._model.action_confirm(move_to_confirm_ids[0]._cr, move_to_confirm_ids[0]._uid, move_to_confirm_ids[0].ids, context=move_to_confirm_ids[0]._context)
            # move_to_confirm_ids[0].action_confirm()
        return res

    @api.model
    def _check(self, procurement):
        ''' Implement the procurement checking for rules of type 'move'. The procurement will be satisfied only if all related
            moves are done/cancel and if the requested quantity is moved.
        '''
        if procurement.rule_id and procurement.rule_id.action == 'move':
            # In case Phantom BoM splits only into procurements
            if not procurement.move_ids:
                return True
            all_done_or_cancel = all([x.state in ('done', 'cancel') for x in procurement.move_ids])
            all_cancel = all([x.state == 'cancel' for x in procurement.move_ids])
            if not all_done_or_cancel:
                return False
            elif all_done_or_cancel and not all_cancel:
                return True
            elif all_cancel:
                procurement.message_post(body=_('All stock moves have been cancelled for this procurement.'))
            procurement.write({'state': 'cancel'})
            return False
        return super(ProcurementOrder, self)._check(procurement)

    @api.multi
    def do_view_pickings(self):
        '''
        This function returns an action that display the pickings of the procurements belonging
        to the same procurement group of given ids.
        '''
        result = self.env.ref('stock.do_view_pickings').read()[0]
        group_ids = set([proc.group_id.id for proc in self if proc.group_id])
        result['domain'] = "[('group_id','in',[" + ','.join(map(str, list(group_ids))) + "])]"
        return result

    @api.model
    def run_scheduler(self, use_new_cursor=False, company_id=False):
        '''
        Call the scheduler in order to check the running procurements (super method), to check the minimum stock rules
        and the availability of moves. This function is intended to be run for all the companies at the same time, so
        we run functions as SUPERUSER to avoid intercompanies and access rights issues.
        @param self: The object pointer
        @param use_new_cursor: if set, use a dedicated cursor and auto-commit after processing each procurement.
            This is appropriate for batch jobs only.
        @param context: A standard dictionary for contextual values
        @return:  Dictionary of values
        '''
        super(ProcurementOrder, self).run_scheduler(use_new_cursor=use_new_cursor, company_id=company_id)
        try:
            if use_new_cursor:
                cr = openerp.registry(self._cr.dbname).cursor()

            move_obj = self.env['stock.move']

            # Minimum stock rules
            self._model._procure_orderpoint_confirm(self._cr, SUPERUSER_ID, use_new_cursor=use_new_cursor, company_id=company_id, context=self._context)

            # Search all confirmed stock_moves and try to assign them
            confirmed_ids = move_obj.search([('state', '=', 'confirmed')], limit=None, order='priority desc, date_expected asc').ids
            for x in xrange(0, len(confirmed_ids), 100):
                move_obj.action_assign(confirmed_ids[x:x + 100])
                if use_new_cursor:
                    cr.commit()

            if use_new_cursor:
                cr.commit()
        finally:
            if use_new_cursor:
                try:
                    cr.close()
                except Exception:
                    pass
        return {}

    @api.model
    def _get_orderpoint_date_planned(self, orderpoint, start_date):
        days = orderpoint.lead_days or 0.0
        if orderpoint.lead_type == 'purchase':
            # These days will be substracted when creating the PO
            days += orderpoint.product_id._select_seller().delay or 0.0
        date_planned = start_date + relativedelta(days=days)
        return date_planned.strftime(DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def _prepare_orderpoint_procurement(self, orderpoint, product_qty):
        return {
            'name': orderpoint.name,
            'date_planned': self._get_orderpoint_date_planned(orderpoint, fields.Date.today()),
            'product_id': orderpoint.product_id.id,
            'product_qty': product_qty,
            'company_id': orderpoint.company_id.id,
            'product_uom': orderpoint.product_uom.id,
            'location_id': orderpoint.location_id.id,
            'origin': orderpoint.name,
            'warehouse_id': orderpoint.warehouse_id.id,
            'orderpoint_id': orderpoint.id,
            'group_id': orderpoint.group_id.id,
        }

    @api.model
    def _procure_orderpoint_confirm(self, use_new_cursor=False, company_id=False):
        '''
        Create procurement based on Orderpoint
        :param bool use_new_cursor: if set, use a dedicated cursor and auto-commit after processing each procurement.
            This is appropriate for batch jobs only.
        '''
        if use_new_cursor:
            cr = openerp.registry(self.env.cr.dbname).cursor()
        Orderpoint = self.env['stock.warehouse.orderpoint']
        Procurement = self.env['procurement.order']

        dom = self.company_id and [('company_id', '=', self.company_id)] or []
        orderpoint_ids = Orderpoint.search(dom, order="location_id")
        ids = orderpoint_ids[:1000]
        prev_ids = []
        tot_procs = []
        for op in orderpoint_ids:
            product_dict = {}
            ops_dict = {}
            key = (op.location_id.id,)
            if not product_dict.get(key):
                    product_dict[key] = [op.product_id]
                    ops_dict[key] = [op]
            else:
                product_dict[key] += [op.product_id]
                ops_dict[key] += [op]
            for key in product_dict.keys():
                self.with_context({'location': ops_dict[key][0].location_id.id})
                prod_qty = [x._product_available() for x in product_dict[key]]
                order_point_ids = Orderpoint.browse([x.id for x in ops_dict[key]])
                subtract_qty = order_point_ids.subtract_procurements_from_orderpoints()
                for op in ops_dict[key]:
                    try:
                        prods = prod_qty[0][op.product_id.id]['virtual_available']
                        if prods is None:
                            continue
                        if float_compare(prods, op.product_min_qty, precision_rounding=op.product_uom.rounding) <= 0:
                            qty = max(op.product_min_qty, op.product_max_qty) - prods
                            reste = op.qty_multiple > 0 and qty % op.qty_multiple or 0.0
                            if float_compare(reste, 0.0, precision_rounding=op.product_uom.rounding) > 0:
                                qty += op.qty_multiple - reste

                            if float_compare(qty, 0.0, precision_rounding=op.product_uom.rounding) < 0:
                                continue

                            qty -= subtract_qty[op.id]

                            qty_rounded = float_round(qty, precision_rounding=op.product_uom.rounding)
                            if qty_rounded > 0:
                                proc_id = Procurement.create(self._prepare_orderpoint_procurement(op, qty_rounded))
                                tot_procs.append(proc_id.id)
                            if use_new_cursor:
                                cr.commit()
                    except OperationalError:
                        if use_new_cursor:
                            orderpoint_ids.append(op.id)
                            cr.rollback()
                            continue
                        else:
                            raise
            try:
                tot_procs.reverse()
                self.run(tot_procs)
                tot_procs = []
                if use_new_cursor:
                    cr.commit()
            except OperationalError:
                if use_new_cursor:
                    cr.rollback()
                    continue
                else:
                    raise

            if use_new_cursor:
                cr.commit()
            if prev_ids == ids:
                break
            else:
                prev_ids = ids

        if use_new_cursor:
            cr.commit()
            cr.close()
        return {}

    @api.v7
    def _procure_orderpoint_confirm(self, cr, uid, use_new_cursor=False, company_id=False, context=None):
        '''
        Create procurement based on Orderpoint
        :param bool use_new_cursor: if set, use a dedicated cursor and auto-commit after processing each procurement.
            This is appropriate for batch jobs only.
        '''
        if context is None:
            context = {}
        if use_new_cursor:
            cr = openerp.registry(cr.dbname).cursor()
        orderpoint_obj = self.pool.get('stock.warehouse.orderpoint')
        procurement_obj = self.pool.get('procurement.order')
        product_obj = self.pool.get('product.product')

        dom = company_id and [('company_id', '=', company_id)] or []
        orderpoint_ids = orderpoint_obj.search(cr, uid, dom, order="location_id")
        prev_ids = []
        tot_procs = []
        while orderpoint_ids:
            ids = orderpoint_ids[:1000]
            del orderpoint_ids[:1000]
            product_dict = {}
            ops_dict = {}
            ops = orderpoint_obj.browse(cr, uid, ids, context=context)

            # Calculate groups that can be executed together
            for op in ops:
                key = (op.location_id.id,)
                if not product_dict.get(key):
                    product_dict[key] = [op.product_id]
                    ops_dict[key] = [op]
                else:
                    product_dict[key] += [op.product_id]
                    ops_dict[key] += [op]

            for key in product_dict.keys():
                ctx = context.copy()
                ctx.update({'location': ops_dict[key][0].location_id.id})
                prod_qty = product_obj._product_available(cr, uid, [x.id for x in product_dict[key]],
                                                          context=ctx)
                subtract_qty = orderpoint_obj.subtract_procurements_from_orderpoints(cr, uid, [x.id for x in ops_dict[key]], context=context)
                for op in ops_dict[key]:
                    try:
                        prods = prod_qty[op.product_id.id]['virtual_available']
                        if prods is None:
                            continue
                        if float_compare(prods, op.product_min_qty, precision_rounding=op.product_uom.rounding) <= 0:
                            qty = max(op.product_min_qty, op.product_max_qty) - prods
                            reste = op.qty_multiple > 0 and qty % op.qty_multiple or 0.0
                            if float_compare(reste, 0.0, precision_rounding=op.product_uom.rounding) > 0:
                                qty += op.qty_multiple - reste

                            if float_compare(qty, 0.0, precision_rounding=op.product_uom.rounding) < 0:
                                continue

                            qty -= subtract_qty[op.id]

                            qty_rounded = float_round(qty, precision_rounding=op.product_uom.rounding)
                            if qty_rounded > 0:
                                proc_id = procurement_obj.create(cr, uid,
                                                                 self._prepare_orderpoint_procurement(cr, uid, op, qty_rounded, context=context),
                                                                 context=context)
                                tot_procs.append(proc_id)
                            if use_new_cursor:
                                cr.commit()
                    except OperationalError:
                        if use_new_cursor:
                            orderpoint_ids.append(op.id)
                            cr.rollback()
                            continue
                        else:
                            raise
            try:
                tot_procs.reverse()
                self.run(cr, uid, tot_procs, context=context)
                tot_procs = []
                if use_new_cursor:
                    cr.commit()
            except OperationalError:
                if use_new_cursor:
                    cr.rollback()
                    continue
                else:
                    raise

            if use_new_cursor:
                cr.commit()
            if prev_ids == ids:
                break
            else:
                prev_ids = ids

        if use_new_cursor:
            cr.commit()
            cr.close()
        return {}
