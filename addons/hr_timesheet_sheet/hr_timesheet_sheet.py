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

    def _total(self):
        """ Compute the attendances, analytic lines timesheets and differences
            between them for all the days of a timesheet and the current day
        """
        res = dict.fromkeys(self.ids, {
            'total_attendance': 0.0,
            'total_timesheet': 0.0,
            'total_difference': 0.0,
        })

        self.env.cr.execute("""
            SELECT sheet_id as id,
                   sum(total_attendance) as total_attendance,
                   sum(total_timesheet) as total_timesheet,
                   sum(total_difference) as  total_difference
            FROM hr_timesheet_sheet_sheet_day
            WHERE sheet_id IN %s
            GROUP BY sheet_id
        """, (tuple(self.ids),))

        res.update(dict((x.pop('id'), x) for x in self.env.cr.dictfetchall()))
        return res

    def check_employee_attendance_state(self):
        """ Checks the attendance records of the timesheet, make sure they are all closed
            (by making sure they have a check_out time)
        """
        if(len(self) > 1):
            print "impossible ! (dskfljqdsf)"
            raise exceptions.UserError(_("NOT GOOD!"))
        if self.env['hr.attendance'].search([('sheet_id', '=', self.id), ('check_out', '=', False)]):
            raise exceptions.UserError(_("The timesheet cannot be validated as it contains an attendance record with no Check Out)."))
        return True

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
            self.check_employee_attendance_state()
            di = sheet.user_id.company_id.timesheet_max_difference
            if (abs(sheet.total_difference) < di) or not di:
                sheet.signal_workflow('confirm')
            else:
                raise exceptions.UserError(_('Please verify that the total difference of the sheet is lower than %.2f.') % (di,))
        return True

    @api.multi # multi no need ? called from xml
    def attendance_action_change(self):
        employee_ids = []
        for sheet in self:
            if sheet.employee_id.id not in employee_ids:
                employee_ids.append(sheet.employee_id.id)
        return self.browse(employee_ids).attendance_action_change()

    def _count_attendances(self): # ??? not sure
        res = {}
        for sheet in self:
            res[sheet.id] = len(sheet.attendances_ids)
        # res = dict.fromkeys(ids, 0)
        # attendances_groups = self.pool['hr.attendance'].read_group(cr, uid, [('sheet_id' , 'in' , ids)], ['sheet_id'], 'sheet_id', context=context)
        # for attendances in attendances_groups:
        #     res[attendances['sheet_id'][0]] = attendances['sheet_id_count']
        return res

    # name had select=1, what is it ?
    name = fields.Char(string="Note", states={'confirm': [('readonly', True)], 'done': [('readonly', True)]})
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    user_id = fields.Many2one('res.users', domain=('id', '=', employee_id.user_id.id), string='User', store=True, readonly=True) # required=False, not necessary, right ?
    date_from = fields.Date('Date From', required=True, readonly=True, states={'new': [('readonly', False)]})

    state = fields.Selection([
        ('new', 'New'),
        ('draft', 'Open'),
        ('confirm', 'Waiting Approval'),
        ('done', 'Approved')], string='Status', required=True, readonly=True,
        track_visibility='onchange',
        help=' * The \'Draft\' status is used when a user is encoding a new and unconfirmed timesheet. \
            \n* The \'Confirmed\' status is used for to confirm the timesheet by user. \
            \n* The \'Done\' status is used when users timesheet is accepted by his/her senior.'),
    
# _columns = {
#     'name': fields.char('Note', select=1,
#                         states={'confirm':[('readonly', True)], 'done':[('readonly', True)]}),
#     'employee_id': fields.many2one('hr.employee', 'Employee', required=True),
#     'user_id': fields.related('employee_id', 'user_id', type="many2one", relation="res.users", store=True, string="User", required=False, readonly=True),
#                     #fields.many2one('res.users', 'User', required=True, select=1, states={'confirm':[('readonly', True)], 'done':[('readonly', True)]}),
#     'date_from': fields.date('Date from', required=True, select=1, readonly=True, states={'new':[('readonly', False)]}),
#     'date_to': fields.date('Date to', required=True, select=1, readonly=True, states={'new':[('readonly', False)]}),
#     'timesheet_ids' : fields.one2many('account.analytic.line', 'sheet_id',
#         'Timesheet lines',
#         readonly=True, states={
#             'draft': [('readonly', False)],
#             'new': [('readonly', False)]}
#         ),
#     'attendances_ids' : fields.one2many('hr.attendance', 'sheet_id', 'Attendances'),
#     'state' : fields.selection([
#         ('new', 'New'),
#         ('draft','Open'),
#         ('confirm','Waiting Approval'),
#         ('done','Approved')], 'Status', select=True, required=True, readonly=True,
#         track_visibility='onchange',
#         help=' * The \'Draft\' status is used when a user is encoding a new and unconfirmed timesheet. \
#             \n* The \'Confirmed\' status is used for to confirm the timesheet by user. \
#             \n* The \'Done\' status is used when users timesheet is accepted by his/her senior.'),
#     'state_attendance' : fields.related('employee_id', 'state', type='selection', selection=[('absent', 'Absent'), ('present', 'Present')], string='Current Status', readonly=True),
#     'total_attendance': fields.function(_total, method=True, string='Total Attendance', multi="_total"),
#     'total_timesheet': fields.function(_total, method=True, string='Total Timesheet', multi="_total"),
#     'total_difference': fields.function(_total, method=True, string='Difference', multi="_total"),
#     'period_ids': fields.one2many('hr_timesheet_sheet.sheet.day', 'sheet_id', 'Period', readonly=True),
#     'account_ids': fields.one2many('hr_timesheet_sheet.sheet.account', 'sheet_id', 'Analytic accounts', readonly=True),
#     'company_id': fields.many2one('res.company', 'Company'),
#     'department_id':fields.many2one('hr.department','Department'),
#     'attendance_count': fields.function(_count_attendances, type='integer', string="Attendances"),
# }

    @api.multi
    def _sheet_date(self, forced_user_id=False):
        for sheet in self:
            new_user_id = forced_user_id or sheet.employee_id.user_id and sheet.employee_id.user_id.id
            if new_user_id:
                self.env.cr.execute('SELECT id \
                    FROM hr_timesheet_sheet_sheet \
                    WHERE (date_from <= %s and %s <= date_to) \
                        AND user_id=%s \
                        AND id <> %s', (sheet.date_to, sheet.date_from, new_user_id, sheet.id))
                if self.env.cr.fetchall():
                    return False
        return True

    # _constraints = [
    #     (_sheet_date, 'You cannot have 2 timesheets that overlap!\nPlease use the menu \'My Current Timesheet\' to avoid this problem.', ['date_from','date_to']),
    # ] DEPRECATED => we use @api.constrains :
    @api.one
    @api.constrains('date_to', 'date_from', 'user_id', 'id')
    def _check_sheet_date(self):
        if self._sheet_date():
            raise exceptions.ValidationError('You cannot have 2 timesheets that overlap!\nPlease use the menu \'My Current Timesheet\' to avoid this problem.')
