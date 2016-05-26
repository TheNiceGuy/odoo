# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp.osv import fields, osv
 from openerp.tools.translate import _
 from openerp.exceptions import UserError


class account_analytic_line(models.Model):
    _inherit = "account.analytic.line"

    @api.depends('date', 'user_id', 'sheet_id.date_to', 'sheet_id.date_from', 'sheet_id.employee_id')
    def _sheet(self):
        """Links the timesheet line to the corresponding sheet
        """
        sheet_obj = self.env['hr_timesheet_sheet.sheet']
        for ts_line in self:
            sheets = sheet_obj.search(
                [('date_to', '>=', ts_line.date), ('date_from', '<=', ts_line.date),
                 ('employee_id.user_id', '=', ts_line.user_id.id),
                 ('state', 'in', ['draft', 'new'])])
            if sheets:
                # [0] because only one sheet possible for an employee between 2 dates
                ts_line.sheet_id = sheets[0]

    def _search_sheet(self, operator, value):
        assert operator == 'in'
        ids = []
        for ts in self.env['hr_timesheet_sheet.sheet'].browse(value):
            self._cr.execute("""
                    SELECT l.id
                        FROM account_analytic_line l
                    WHERE %(date_to)s >= l.date
                        AND %(date_from)s <= l.date
                        AND %(user_id)s = l.user_id
                    GROUP BY l.id""", {'date_from': ts.date_from,
                                        'date_to': ts.date_to,
                                        'user_id': ts.employee_id.user_id.id,})
            ids.extend([row[0] for row in self._cr.fetchall()])
        return [('id', 'in', ids)]

    # à priori le search ne fonctionnera pas car store=True donc il ira voir tt de suite dans la colonne, faudra sans doute
    # créer une 2ème variable non storée qui la suit...
    sheet_id = fields.Many2one('hr_timesheet_sheet.sheet', string='Sheet', compute='_sheet', index=True, ondelete='cascade',
        store=True, search='_search_sheet')

    @api.multi
    def write(self, values):
        self._check()
        return super(account_analytic_line, self).write(values)

    @api.multi
    def unlink(self):
        self._check()
        return super(account_analytic_line, self).unlink()

    def _check(self):
        for line in self:
            if line.sheet_id and line.sheet_id.state not in ('draft', 'new'):
                raise UserError(_('You cannot modify an entry in a confirmed timesheet.'))
        return True
