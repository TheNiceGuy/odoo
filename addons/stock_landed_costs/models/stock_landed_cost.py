# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import SUPERUSER_ID

from odoo import api, fields, models, tools, _
from odoo.addons import decimal_precision as dp
from odoo.addons.stock_landed_costs import product
from odoo.exceptions import UserError


class LandedCost(models.Model):
    _name = 'stock.landed.cost'
    _description = 'Stock Landed Cost'
    _inherit = 'mail.thread'

    name = fields.Char(
        'Name', default=lambda self: self.env['ir.sequence'].next_by_code('stock.landed.cost'),
        copy=False, readonly=True, track_visibility='always')
    date = fields.Date(
        'Date', default=fields.Date.context_today,
        copy=False, required=True, states={'done': [('readonly', True)]}, track_visibility='onchange')
    picking_ids = fields.Many2many(
        'stock.picking', string='Pickings',
        copy=False, states={'done': [('readonly', True)]})
    cost_lines = fields.one2many(
        'stock.landed.cost.lines', 'cost_id', 'Cost Lines',
        copy=True, states={'done': [('readonly', True)]})
    valuation_adjustment_lines = fields.One2many(
        'stock.valuation.adjustment.lines', 'cost_id', 'Valuation Adjustments',
        states={'done': [('readonly', True)]})
    description = fields.Text(
        'Item Description', states={'done': [('readonly', True)]})
    amount_total = fields.Float(
        'Total', compute='_compute_total_amount',
        digits=0, track_visibility='always')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Posted'),
        ('cancel', 'Cancelled')], 'State', default='draft',
        copy=False, readonly=True, track_visibility='onchange')
    account_move_id = fields.Many2one(
        'account.move', 'Journal Entry',
        copy=False, readonly=True)
    account_journal_id = fields.Many2one(
        'account.journal', 'Account Journal',
        required=True, states={'done': [('readonly', True)]})

    @api.one
    @api.depends('cost_lines.price_unit')
    def _compute_total_amount(self):
        self.total_amount = sum(line.price_unit for line in self.cost_lines)

    @api.multi
    def unlink(self):
        self.button_cancel()
        return super(LandedCost, self).unlink()

    @api.multi
    def _track_subtype(self, init_values):
        if 'state' in init_values and self.state == 'done':
            return 'stock_landed_costs.mt_stock_landed_cost_open'
        return super(LandedCost, self)._track_subtype(init_values)

    @api.multi
    def button_cancel(self):
        if any(cost.state == 'done' for cost in self):
            raise UserError(
                _('Validated landed costs cannot be cancelled, '
                  'but you could create negative landed costs to reverse them'))
        return self.write({'state': 'cancel'})


    def _create_accounting_entries(self, cr, uid, line, move_id, qty_out, context=None):
        product_obj = self.pool.get('product.template')
        cost_product = line.cost_line_id and line.cost_line_id.product_id
        if not cost_product:
            return False
        accounts = product_obj.browse(cr, uid, line.product_id.product_tmpl_id.id, context=context).get_product_accounts()
        debit_account_id = accounts.get('stock_valuation', False) and accounts['stock_valuation'].id or False
        already_out_account_id = accounts['stock_output'].id
        credit_account_id = line.cost_line_id.account_id.id or cost_product.property_account_expense_id.id or cost_product.categ_id.property_account_expense_categ_id.id

        if not credit_account_id:
            raise UserError(_('Please configure Stock Expense Account for product: %s.') % (cost_product.name))

        return self._create_account_move_line(cr, uid, line, move_id, credit_account_id, debit_account_id, qty_out, already_out_account_id, context=context)

    def _create_account_move_line(self, cr, uid, line, move_id, credit_account_id, debit_account_id, qty_out, already_out_account_id, context=None):
        """
        Generate the account.move.line values to track the landed cost.
        Afterwards, for the goods that are already out of stock, we should create the out moves
        """
        aml_obj = self.pool.get('account.move.line')
        user_obj = self.pool.get('res.users')
        if context is None:
            context = {}
        ctx = context.copy()
        ctx['check_move_validity'] = False
        base_line = {
            'name': line.name,
            'move_id': move_id,
            'product_id': line.product_id.id,
            'quantity': line.quantity,
        }
        debit_line = dict(base_line, account_id=debit_account_id)
        credit_line = dict(base_line, account_id=credit_account_id)
        diff = line.additional_landed_cost
        if diff > 0:
            debit_line['debit'] = diff
            credit_line['credit'] = diff
        else:
            # negative cost, reverse the entry
            debit_line['credit'] = -diff
            credit_line['debit'] = -diff
        aml_obj.create(cr, uid, debit_line, context=ctx)
        aml_obj.create(cr, uid, credit_line, context=ctx)
        
        #Create account move lines for quants already out of stock
        if qty_out > 0:
            debit_line = dict(base_line,
                              name=(line.name + ": " + str(qty_out) + _(' already out')),
                              quantity=qty_out,
                              account_id=already_out_account_id)
            credit_line = dict(base_line,
                              name=(line.name + ": " + str(qty_out) + _(' already out')),
                              quantity=qty_out,
                              account_id=debit_account_id)
            diff = diff * qty_out / line.quantity
            if diff > 0:
                debit_line['debit'] = diff
                credit_line['credit'] = diff
            else:
                # negative cost, reverse the entry
                debit_line['credit'] = -diff
                credit_line['debit'] = -diff
            aml_obj.create(cr, uid, debit_line, context=ctx)
            aml_obj.create(cr, uid, credit_line, context=ctx)

            if user_obj.browse(cr, uid, [uid], context=context).company_id.anglo_saxon_accounting:
                debit_line = dict(base_line,
                                  name=(line.name + ": " + str(qty_out) + _(' already out')),
                                  quantity=qty_out,
                                  account_id=credit_account_id)
                credit_line = dict(base_line,
                                  name=(line.name + ": " + str(qty_out) + _(' already out')),
                                  quantity=qty_out,
                                  account_id=already_out_account_id)

                if diff > 0:
                    debit_line['debit'] = diff
                    credit_line['credit'] = diff
                else:
                    # negative cost, reverse the entry
                    debit_line['credit'] = -diff
                    credit_line['debit'] = -diff
                aml_obj.create(cr, uid, debit_line, context=ctx)
                aml_obj.create(cr, uid, credit_line, context=ctx)

        self.pool.get('account.move').assert_balanced(cr, uid, [move_id], context=context)
        return True

    def _create_account_move(self, cr, uid, cost, context=None):
        vals = {
            'journal_id': cost.account_journal_id.id,
            'date': cost.date,
            'ref': cost.name
        }
        return self.pool.get('account.move').create(cr, uid, vals, context=context)

    def _check_sum(self, cr, uid, landed_cost, context=None):
        """
        Will check if each cost line its valuation lines sum to the correct amount
        and if the overall total amount is correct also
        """
        costcor = {}
        tot = 0
        for valuation_line in landed_cost.valuation_adjustment_lines:
            if costcor.get(valuation_line.cost_line_id):
                costcor[valuation_line.cost_line_id] += valuation_line.additional_landed_cost
            else:
                costcor[valuation_line.cost_line_id] = valuation_line.additional_landed_cost
            tot += valuation_line.additional_landed_cost

        prec = self.pool['decimal.precision'].precision_get(cr, uid, 'Account')
        # float_compare returns 0 for equal amounts
        res = not bool(tools.float_compare(tot, landed_cost.amount_total, precision_digits=prec))
        for costl in costcor.keys():
            if tools.float_compare(costcor[costl], costl.price_unit, precision_digits=prec):
                res = False
        return res

    def button_validate(self, cr, uid, ids, context=None):
        quant_obj = self.pool.get('stock.quant')

        for cost in self.browse(cr, uid, ids, context=context):
            if cost.state != 'draft':
                raise UserError(_('Only draft landed costs can be validated'))
            if not cost.valuation_adjustment_lines or not self._check_sum(cr, uid, cost, context=context):
                raise UserError(_('You cannot validate a landed cost which has no valid valuation adjustments lines. Did you click on Compute?'))
            move_id = self._create_account_move(cr, uid, cost, context=context)
            for line in cost.valuation_adjustment_lines:
                if not line.move_id:
                    continue
                per_unit = line.final_cost / line.quantity
                diff = per_unit - line.former_cost_per_unit

                # If the precision required for the variable diff is larger than the accounting
                # precision, inconsistencies between the stock valuation and the accounting entries
                # may arise.
                # For example, a landed cost of 15 divided in 13 units. If the products leave the
                # stock one unit at a time, the amount related to the landed cost will correspond to
                # round(15/13, 2)*13 = 14.95. To avoid this case, we split the quant in 12 + 1, then
                # record the difference on the new quant.
                # We need to make sure to able to extract at least one unit of the product. There is
                # an arbitrary minimum quantity set to 2.0 from which we consider we can extract a
                # unit and adapt the cost.
                curr_rounding = line.move_id.company_id.currency_id.rounding
                diff_rounded = tools.float_round(diff, precision_rounding=curr_rounding)
                diff_correct = diff_rounded
                quants = line.move_id.quant_ids.sorted(key=lambda r: r.qty, reverse=True)
                quant_correct = False
                if quants\
                        and tools.float_compare(quants[0].product_id.uom_id.rounding, 1.0, precision_digits=1) == 0\
                        and tools.float_compare(line.quantity * diff, line.quantity * diff_rounded, precision_rounding=curr_rounding) != 0\
                        and tools.float_compare(quants[0].qty, 2.0, precision_rounding=quants[0].product_id.uom_id.rounding) >= 0:
                    # Search for existing quant of quantity = 1.0 to avoid creating a new one
                    quant_correct = quants.filtered(lambda r: tools.float_compare(r.qty, 1.0, precision_rounding=quants[0].product_id.uom_id.rounding) == 0)
                    if not quant_correct:
                        quant_correct = quants[0]._quant_split(quants[0].qty - 1.0)
                    else:
                        quant_correct = quant_correct[0]
                        quants = quants - quant_correct
                    diff_correct += (line.quantity * diff) - (line.quantity * diff_rounded)
                    diff = diff_rounded

                quant_dict = {}
                for quant in quants:
                    quant_dict[quant.id] = quant.cost + diff
                if quant_correct:
                    quant_dict[quant_correct.id] = quant_correct.cost + diff_correct
                for key, value in quant_dict.items():
                    quant_obj.write(cr, SUPERUSER_ID, key, {'cost': value}, context=context)
                qty_out = 0
                for quant in line.move_id.quant_ids:
                    if quant.location_id.usage != 'internal':
                        qty_out += quant.qty
                self._create_accounting_entries(cr, uid, line, move_id, qty_out, context=context)
            self.write(cr, uid, cost.id, {'state': 'done', 'account_move_id': move_id}, context=context)
            self.pool.get('account.move').post(cr, uid, [move_id], context=context)
        return True

    def get_valuation_lines(self, cr, uid, ids, picking_ids=None, context=None):
        picking_obj = self.pool.get('stock.picking')
        lines = []
        if not picking_ids:
            return lines

        for picking in picking_obj.browse(cr, uid, picking_ids):
            for move in picking.move_lines:
                #it doesn't make sense to make a landed cost for a product that isn't set as being valuated in real time at real cost
                if move.product_id.valuation != 'real_time' or move.product_id.cost_method != 'real':
                    continue
                total_cost = 0.0
                weight = move.product_id and move.product_id.weight * move.product_qty
                volume = move.product_id and move.product_id.volume * move.product_qty
                for quant in move.quant_ids:
                    total_cost += quant.cost * quant.qty
                vals = dict(product_id=move.product_id.id, move_id=move.id, quantity=move.product_qty, former_cost=total_cost, weight=weight, volume=volume)
                lines.append(vals)
        if not lines:
            raise UserError(_('The selected picking does not contain any move that would be impacted by landed costs. Landed costs are only possible for products configured in real time valuation with real price costing method. Please make sure it is the case, or you selected the correct picking'))
        return lines

    def compute_landed_cost(self, cr, uid, ids, context=None):
        line_obj = self.pool.get('stock.valuation.adjustment.lines')
        unlink_ids = line_obj.search(cr, uid, [('cost_id', 'in', ids)], context=context)
        line_obj.unlink(cr, uid, unlink_ids, context=context)
        digits = dp.get_precision('Product Price')(cr)
        towrite_dict = {}
        for cost in self.browse(cr, uid, ids, context=None):
            if not cost.picking_ids:
                continue
            picking_ids = [p.id for p in cost.picking_ids]
            total_qty = 0.0
            total_cost = 0.0
            total_weight = 0.0
            total_volume = 0.0
            total_line = 0.0
            vals = self.get_valuation_lines(cr, uid, [cost.id], picking_ids=picking_ids, context=context)
            for v in vals:
                for line in cost.cost_lines:
                    v.update({'cost_id': cost.id, 'cost_line_id': line.id})
                    self.pool.get('stock.valuation.adjustment.lines').create(cr, uid, v, context=context)
                total_qty += v.get('quantity', 0.0)
                total_cost += v.get('former_cost', 0.0)
                total_weight += v.get('weight', 0.0)
                total_volume += v.get('volume', 0.0)
                total_line += 1

            for line in cost.cost_lines:
                value_split = 0.0
                for valuation in cost.valuation_adjustment_lines:
                    value = 0.0
                    if valuation.cost_line_id and valuation.cost_line_id.id == line.id:
                        if line.split_method == 'by_quantity' and total_qty:
                            per_unit = (line.price_unit / total_qty)
                            value = valuation.quantity * per_unit
                        elif line.split_method == 'by_weight' and total_weight:
                            per_unit = (line.price_unit / total_weight)
                            value = valuation.weight * per_unit
                        elif line.split_method == 'by_volume' and total_volume:
                            per_unit = (line.price_unit / total_volume)
                            value = valuation.volume * per_unit
                        elif line.split_method == 'equal':
                            value = (line.price_unit / total_line)
                        elif line.split_method == 'by_current_cost_price' and total_cost:
                            per_unit = (line.price_unit / total_cost)
                            value = valuation.former_cost * per_unit
                        else:
                            value = (line.price_unit / total_line)

                        if digits:
                            value = tools.float_round(value, precision_digits=digits[1], rounding_method='UP')
                            fnc = min if line.price_unit > 0 else max
                            value = fnc(value, line.price_unit - value_split)
                            value_split += value

                        if valuation.id not in towrite_dict:
                            towrite_dict[valuation.id] = value
                        else:
                            towrite_dict[valuation.id] += value
        if towrite_dict:
            for key, value in towrite_dict.items():
                line_obj.write(cr, uid, key, {'additional_landed_cost': value}, context=context)
        return True


class LandedCostLine(models.Model):
    _name = 'stock.landed.cost.lines'
    _description = 'Stock Landed Cost Lines'

    name = fields.Char('Description')
    cost_id = fields.Many2one(
        'stock.landed.cost', 'Landed Cost',
        required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    price_unit = fields.Float(
        'Cost', digits_compute=dp.get_precision('Product Price'),
        required=True)
    split_method = fields.Selection(
        product.SPLIT_METHOD, string='Split Method',
        required=True)
    account_id = fields.Many2one(
        'account.account', 'Account',
        domain=[('internal_type', '!=', 'view'), ('internal_type', '!=', 'closed'), ('deprecated', '=', False)])

    @api.onchange('product_id')
    def onchange_product_id(self):
        if not self.product_id:
            self.quantity = 0.0
        self.name = self.product_id.name or ''
        self.split_method = self.product_id.split_method or 'equal'
        self.price_unit = self.product_id.standard_price or 0.0
        self.account_id = self.product_id.roperty_account_expense_id.id or self.product_id.categ_id.property_account_expense_categ_id.id or False


class AdjustmentLines(models.Model):
    _name = 'stock.valuation.adjustment.lines'
    _description = 'Stock Valuation Adjustment Lines'

    name = fields.Char(
        'Description', compute='_compute_name', store=True)
    cost_id = fields.Many2one(
        'stock.landed.cost', 'Landed Cost',
        ondelete='cascade', required=True)
    cost_line_id = fields.Many2one(
        'stock.landed.cost.lines', 'Cost Line', readonly=True)
    move_id = fields.Many2one(
        'stock.move', 'Stock Move', readonly=True)
    product_id = fields.Many2one(
        'product.product', 'Product', required=True)
    quantity = fields.Float(
        'Quantity', default=1.0,
        digits_compute=dp.get_precision('Product Unit of Measure'),
        required=True)
    weight = fields.Float(
        'Weight', default=1.0,
        digits_compute=dp.get_precision('Product Unit of Measure'))
    volume = fields.Float(
        'Volume', default=1.0,
        digits_compute=dp.get_precision('Product Unit of Measure'))
    former_cost = fields.Float(
        'Former Cost', digits_compute=dp.get_precision('Product Price'))
    former_cost_per_unit = fields.Float(
        'Former Cost(Per Unit)', compute='_compute_former_cost_per_unit', store=True,
        digits=0)
    additional_landed_cost = fields.Float(
        'Additional Landed Cost',
        digits_compute=dp.get_precision('Product Price'))
    final_cost = fields.Float(
        'Final Cost', compute='_compute_final_cost', store=True,
        digits=0)

    @api.one
    @api.depends('cost_line_id.name', 'product_id.code', 'product_id.name')
    def _compute_name(self):
        name =  '%s - ' % self.cost_line_id.name if self.cost_line_id else ''
        self.name = name + self.product_id.code or self.product_id.name or ''

    @api.one
    @api.depends('former_cost', 'quantity')
    def _compute_former_cost_per_unit(self):
        self.former_cost_per_unit = self.former_cost / (self.quantity or 1.0)

    @api.one
    @api.depends('former_cost_per_unit', 'additional_landed_cost')
    def _compute_final_cost(self):
        self.final_cost = self.former_cost_per_unit + self.additional_landed_cost
