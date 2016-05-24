# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
import pytz

from openerp import api, fields, models, exceptions
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.translate import _
from openerp.exceptions import UserError


class hr_timesheet_sheet(models.Model):
    _name = "hr_timesheet_sheet.sheet"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _table = 'hr_timesheet_sheet_sheet' # superflu, non?
    _order = "id desc"
    _description = "Timesheet"

    @api.depends('period_ids.total_attendance', 'period_ids.total_timesheet', 'period_ids.total_difference')
    def _total(self):
        """ Compute the attendances, analytic lines timesheets and differences
            between them for all the days of a timesheet and the current day
        """

        self.env.cr.execute("""
            SELECT sheet_id as id,
                   sum(total_attendance) as total_attendance,
                   sum(total_timesheet) as total_timesheet,
                   sum(total_difference) as  total_difference
            FROM hr_timesheet_sheet_sheet_day
            WHERE sheet_id IN %s
            GROUP BY sheet_id
        """, (tuple(self.ids),))

        for x in self.env.cr.dictfetchall():
            sheet = self.browse(x.pop('id'))
            # sheet.total_attendance = x.pop('total_attendance')
            sheet.total_timesheet = x.pop('total_timesheet')
            # sheet.total_difference = x.pop('total_difference')

    # def check_employee_attendance_state(self):
    #     """ Checks the attendance records of the timesheet, make sure they are all closed
    #         (by making sure they have a check_out time)
    #     """
    #     if any(self.attendances_ids.filtered(lambda r: not r.check_out)):
    #         raise exceptions.UserError(_("The timesheet cannot be validated as it contains an attendance record with no Check Out)."))
    #     return True

    def copy(self, *args, **argv):
        raise UserError(_('You cannot duplicate a timesheet.'))

    @api.model
    def create(self, vals):
        if 'employee_id' in vals:
            if not self.env['hr.employee'].browse(vals['employee_id']).user_id:
                raise UserError(_('In order to create a timesheet for this employee, you must link him/her to a user.'))
        # No more need to sort the attendances, except for user lookupability maybe ...
        return super(hr_timesheet_sheet, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'employee_id' in vals:
            new_user_id = self.env['hr.employee'].browse(vals['employee_id']).user_id.id # Pourquoi il y avait or False avant
            if not new_user_id:
                raise UserError(_('In order to create a timesheet for this employee, you must link him/her to a user.'))
            if not self._sheet_date(forced_user_id=new_user_id):
                raise UserError(_('You cannot have 2 timesheets that overlap!\nYou should use the menu \'My Timesheet\' to avoid this problem.'))
            #   I don't a product_id field defined to hr.employee anywhere. (and why would it be used for?)
            # if not self.env['hr.employee'].browse(vals['employee_id']).product_id:
            #     raise UserError(_('In order to create a timesheet for this employee, you must link the employee to a product.'))
            #   No more need to sort.
        return super(hr_timesheet_sheet, self).write(vals)

    @api.multi # multi no need ? called from xml/yml
    def button_confirm(self):
        for sheet in self:
            if sheet.employee_id and sheet.employee_id.parent_id and sheet.employee_id.parent_id.user_id:
                self.message_subscribe_users(user_ids=[sheet.employee_id.parent_id.user_id.id])
            # self.check_employee_attendance_state()
            # di = sheet.user_id.company_id.timesheet_max_difference
            # if (abs(sheet.total_difference) < di) or not di:
            sheet.signal_workflow('confirm')
            # else:
            #     raise exceptions.UserError(_('Please verify that the total difference of the sheet is lower than %.2f.') % (di,))
        return True

    # @api.multi # multi no need ? called from xml
    # def attendance_action_change(self):
    #     employee_ids = []
    #     for sheet in self:
    #         if sheet.employee_id.id not in employee_ids:
    #             employee_ids.append(sheet.employee_id.id)
    #     return self.browse(employee_ids).attendance_action_change()

    # @api.depends('attendances_ids')
    # def _count_attendances(self):
    #     res = {}
    #     for sheet in self:
    #         res[sheet.id] = len(sheet.attendances_ids)
    #     return res

    def _default_date_from(self):
        user = self.env['res.users'].browse(self.env.uid)
        r = user.company_id and user.company_id.timesheet_range or 'month'
        if r == 'month':
            return time.strftime('%Y-%m-01')
        elif r == 'week':
            return (datetime.today() + relativedelta(weekday=0, days=-6)).strftime('%Y-%m-%d')
        elif r == 'year':
            return time.strftime('%Y-01-01')
        return fields.date.context_today(self)

    def _default_date_to(self):
        user = self.env['res.users'].browse(self.env.uid)
        r = user.company_id and user.company_id.timesheet_range or 'month'
        if r == 'month':
            return (datetime.today() + relativedelta(months=+1, day=1, days=-1)).strftime('%Y-%m-%d')
        elif r == 'week':
            return (datetime.today() + relativedelta(weekday=6)).strftime('%Y-%m-%d')
        elif r == 'year':
            return time.strftime('%Y-12-31')
        return fields.date.context_today(self)

    def _default_employee(self):
        emp_ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
        return emp_ids and emp_ids[0] or False

    # name had select=1 (= index=True, ) why, no use, is there ???
    name = fields.Char(string="Note", states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    employee_id = fields.Many2one('hr.employee', string='Employee', default=_default_employee, required=True)
    user_id = fields.Many2one('res.users', related='employee_id.user_id', string='User', store=True, readonly=True) # required=False, not necessary, right ?
    date_from = fields.Date(string='Date From', default=_default_date_from, required=True,
        index=True, readonly=True, states={'new': [('readonly', False)]})
    date_to = fields.Date(string='Date To', default=_default_date_to, required=True,
        index=True, readonly=True, states={'new': [('readonly', False)]})
    timesheet_ids = fields.One2many('account.analytic.line', 'sheet_id',
        string='Timesheet lines',
        readonly=True, states={
            'draft': [('readonly', False)],
            'new': [('readonly', False)]})
    # attendances_ids = fields.One2many('hr.attendance', 'sheet_id', 'Attendances')
    state = fields.Selection([
        ('new', 'New'),
        ('draft', 'Open'),
        ('confirm', 'Waiting Approval'),
        ('done', 'Approved')], default='new', track_visibility='onchange',
        string='Status', required=True, readonly=True, index=True,
        help=' * The \'Open\' status is used when a user is encoding a new and unconfirmed timesheet. \
            \n* The \'Waiting Approval\' status is used to confirm the timesheet by user. \
            \n* The \'Approved\' status is used when the users timesheet is accepted by his/her senior.')
    # state_attendance = fields.Selection(string='Current Status', related='employee_id.state',
    #    selection=[('absent', 'Absent'), ('present', 'Present')], readonly=True)
    # total_attendance = fields.Integer(string='Total Attendance', compute='_total')
    total_timesheet = fields.Float(string='Total Timesheet', compute="_total")
    # total_difference = fields.Float(string='Difference', compute="_total")
    period_ids = fields.One2many('hr_timesheet_sheet.sheet.day', 'sheet_id', string='Period', readonly=True)
    account_ids = fields.One2many('hr_timesheet_sheet.sheet.account', 'sheet_id', string='Analytic accounts', readonly=True)
    company_id = fields.Many2one('res.company', string='Company')
    department_id = fields.Many2one('hr.department', string='Department',
        default=lambda self: self.env['res.company']._company_default_get())
    # attendance_count = fields.Integer(compute='_count_attendances', string="Attendances")

    @api.constrains('date_to', 'date_from', 'employee_id')
    def _check_sheet_date(self):
        for sheet in self:
            new_user_id = sheet.user_id and sheet.user_id.id
            if new_user_id:
                self.env.cr.execute('SELECT id \
                    FROM hr_timesheet_sheet_sheet \
                    WHERE (date_from <= %s and %s <= date_to) \
                        AND user_id=%s \
                        AND id <> %s', (sheet.date_to, sheet.date_from, new_user_id, sheet.id))
                if not self.env.cr.fetchall():
                    raise exceptions.ValidationError('You cannot have 2 timesheets that overlap!\nPlease use the menu \'My Current Timesheet\' to avoid this problem.')

    @api.multi
    def action_set_to_draft(self):
        self.write({'state': 'draft'})
        self.create_workflow()
        return True
