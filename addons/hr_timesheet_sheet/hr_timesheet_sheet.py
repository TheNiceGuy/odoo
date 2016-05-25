# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
import pytz

from openerp import api, fields, models
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.translate import _
from openerp.exceptions import UserError, ValidationError


class hr_timesheet_sheet(models.Model):
    _name = "hr_timesheet_sheet.sheet"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _table = 'hr_timesheet_sheet_sheet'
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
    #         raise UserError(_("The timesheet cannot be validated as it contains an attendance record with no Check Out)."))
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
            new_user_id = self.env['hr.employee'].browse(vals['employee_id']).user_id.id
            if not new_user_id:
                raise UserError(_('In order to create a timesheet for this employee, you must link him/her to a user.'))
            if not self._sheet_date(forced_user_id=new_user_id):
                raise UserError(_('You cannot have 2 timesheets that overlap!\nYou should use the menu \'My Timesheet\' to avoid this problem.'))
            # ??? I don't see a product_id field defined to hr.employee anywhere. (and why would it be used for?)
            # if not self.env['hr.employee'].browse(vals['employee_id']).product_id:
            #     raise UserError(_('In order to create a timesheet for this employee, you must link the employee to a product.'))
            #   No more need to sort.
        return super(hr_timesheet_sheet, self).write(vals)

    def button_confirm(self):
        for sheet in self:
            if sheet.employee_id and sheet.employee_id.parent_id and sheet.employee_id.parent_id.user_id:
                self.message_subscribe_users(user_ids=[sheet.employee_id.parent_id.user_id.id])
            # self.check_employee_attendance_state()
            # di = sheet.user_id.company_id.timesheet_max_difference
            # if (abs(sheet.total_difference) < di) or not di:
            sheet.signal_workflow('confirm')
            # else:
            #     raise UserError(_('Please verify that the total difference of the sheet is lower than %.2f.') % (di,))
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
    def _sheet_date(self):
        for sheet in self:
            new_user_id = sheet.user_id and sheet.user_id.id
            if new_user_id:
                self.env.cr.execute('SELECT id \
                    FROM hr_timesheet_sheet_sheet \
                    WHERE (date_from <= %s and %s <= date_to) \
                        AND user_id=%s \
                        AND id <> %s', (sheet.date_to, sheet.date_from, new_user_id, sheet.id))
                if not self.env.cr.fetchall():
                    raise ValidationError('You cannot have 2 timesheets that overlap!\nPlease use the menu \'My Current Timesheet\' to avoid this problem.')

    @api.multi
    def action_set_to_draft(self):
        self.write({'state': 'draft'})
        self.create_workflow()
        return True

    @api.multi
    def name_get(self):
        # week number according to ISO 8601 Calendar
        return [(r['id'], _('Week ')+str(datetime.strptime(r['date_from'], '%Y-%m-%d').isocalendar()[1])) \
            for r in self.read(['date_from'], load='_classic_write')]

    @api.multi
    def unlink(self):
        # sheets = self.read(cr, uid, ids, ['state','total_attendance'], context=context)
        sheets = self.read(['state'])
        for sheet in sheets:
            if sheet['state'] in ('confirm', 'done'):
                raise UserError(_('You cannot delete a timesheet which is already confirmed.'))
            # elif sheet['total_attendance'] <> 0.00:
            #     raise UserError(_('You cannot delete a timesheet which have attendance entries.'))

        analytic_timesheet_toremove = self.env['account.analytic.line']
        for sheet in self:
            analytic_timesheet_toremove += sheet.timesheet_ids
        analytic_timesheet_toremove.unlink()

        return super(hr_timesheet_sheet, self).unlink()

    @api.onchange('hr_employee')
    def onchange_employee_id(self):
        if self.employee_id:
            self.department_id = self.employee_id.department_id
            self.user_id = self.employee_id.user_id

    # ------------------------------------------------
    # OpenChatter methods and notifications
    # ------------------------------------------------

    @api.multi
    def _track_subtype(self, init_values):
        if self:
            record = self[0]
            if 'state' in init_values and record.state == 'confirm':
                return 'hr_timesheet_sheet.mt_timesheet_confirmed'
            elif 'state' in init_values and record.state == 'done':
                return 'hr_timesheet_sheet.mt_timesheet_approved'
        return super(hr_timesheet_sheet, self)._track_subtype(init_values)

    @api.model
    def _needaction_domain_get(self):
        empids = self.env['hr.employee'].search([('parent_id.user_id', '=', self.env.uid)])
        if not empids:
            return False
        return ['&', ('state', '=', 'confirm'), ('employee_id', 'in', empids)]


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


class hr_attendance(models.Model):
    _inherit = "hr.attendance"
#--------
    def _get_default_date(self, cr, uid, context=None):
        if context is None:
            context = {}
        if 'name' in context:
            return context['name'] + time.strftime(' %H:%M:%S')
        return time.strftime('%Y-%m-%d %H:%M:%S')

    def _get_hr_timesheet_sheet(self, cr, uid, ids, context=None):
        attendance_ids = []
        for ts in self.browse(cr, uid, ids, context=context):
            cr.execute("""
                        SELECT a.id
                          FROM hr_attendance a
                         INNER JOIN hr_employee e
                               INNER JOIN resource_resource r
                                       ON (e.resource_id = r.id)
                            ON (a.employee_id = e.id)
                         LEFT JOIN res_users u
                         ON r.user_id = u.id
                         LEFT JOIN res_partner p
                         ON u.partner_id = p.id
                         WHERE %(date_to)s >= date_trunc('day', a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC'))
                              AND %(date_from)s <= date_trunc('day', a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC'))
                              AND %(user_id)s = r.user_id
                         GROUP BY a.id""", {'date_from': ts.date_from,
                                            'date_to': ts.date_to,
                                            'user_id': ts.employee_id.user_id.id,})
            attendance_ids.extend([row[0] for row in cr.fetchall()])
        return attendance_ids

    def _get_attendance_employee_tz(self, cr, uid, employee_id, date, context=None):
        """ Simulate timesheet in employee timezone

        Return the attendance date in string format in the employee
        tz converted from utc timezone as we consider date of employee
        timesheet is in employee timezone
        """
        employee_obj = self.pool['hr.employee']

        tz = False
        if employee_id:
            employee = employee_obj.browse(cr, uid, employee_id, context=context)
            tz = employee.user_id.partner_id.tz

        if not date:
            date = time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        att_tz = timezone(tz or 'utc')

        attendance_dt = datetime.strptime(date, DEFAULT_SERVER_DATETIME_FORMAT)
        att_tz_dt = pytz.utc.localize(attendance_dt)
        att_tz_dt = att_tz_dt.astimezone(att_tz)
        # We take only the date omiting the hours as we compare with timesheet
        # date_from which is a date format thus using hours would lead to
        # be out of scope of timesheet
        att_tz_date_str = datetime.strftime(att_tz_dt, DEFAULT_SERVER_DATE_FORMAT)
        return att_tz_date_str

    def _get_current_sheet(self, cr, uid, employee_id, date=False, context=None):

        sheet_obj = self.pool['hr_timesheet_sheet.sheet']
        if not date:
            date = time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        att_tz_date_str = self._get_attendance_employee_tz(
                cr, uid, employee_id,
                date=date, context=context)
        sheet_ids = sheet_obj.search(cr, uid,
            [('date_from', '<=', att_tz_date_str),
             ('date_to', '>=', att_tz_date_str),
             ('employee_id', '=', employee_id)],
            limit=1, context=context)
        return sheet_ids and sheet_ids[0] or False

    def _sheet(self, cursor, user, ids, name, args, context=None):
        res = {}.fromkeys(ids, False)
        for attendance in self.browse(cursor, user, ids, context=context):
            res[attendance.id] = self._get_current_sheet(
                    cursor, user, attendance.employee_id.id, attendance.name,
                    context=context)
        return res

    _columns = {
        'sheet_id': fields.function(_sheet, string='Sheet',
            type='many2one', relation='hr_timesheet_sheet.sheet',
            store={
                      'hr_timesheet_sheet.sheet': (_get_hr_timesheet_sheet, ['employee_id', 'date_from', 'date_to'], 10),
                      'hr.attendance': (lambda self,cr,uid,ids,context=None: ids, ['employee_id', 'name', 'day'], 10),
                  },
            )
    }
    _defaults = {
        'name': _get_default_date,
    }

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}

        sheet_id = context.get('sheet_id') or self._get_current_sheet(cr, uid, vals.get('employee_id'), vals.get('name'), context=context)
        if sheet_id:
            att_tz_date_str = self._get_attendance_employee_tz(
                    cr, uid, vals.get('employee_id'),
                   date=vals.get('name'), context=context)
            ts = self.pool.get('hr_timesheet_sheet.sheet').browse(cr, uid, sheet_id, context=context)
            if ts.state not in ('draft', 'new'):
                raise UserError(_('You can not enter an attendance in a submitted timesheet. Ask your manager to reset it before adding attendance.'))
            elif ts.date_from > att_tz_date_str or ts.date_to < att_tz_date_str:
                raise UserError(_('You can not enter an attendance date outside the current timesheet dates.'))
        return super(hr_attendance,self).create(cr, uid, vals, context=context)

    def unlink(self, cr, uid, ids, *args, **kwargs):
        if isinstance(ids, (int, long)):
            ids = [ids]
        self._check(cr, uid, ids)
        return super(hr_attendance,self).unlink(cr, uid, ids,*args, **kwargs)

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        self._check(cr, uid, ids)
        res = super(hr_attendance,self).write(cr, uid, ids, vals, context=context)
        if 'sheet_id' in context:
            for attendance in self.browse(cr, uid, ids, context=context):
                if context['sheet_id'] != attendance.sheet_id.id:
                    raise UserError(_('You cannot enter an attendance ' \
                            'date outside the current timesheet dates.'))
        return res

    def _check(self, cr, uid, ids):
        for att in self.browse(cr, uid, ids):
            if att.sheet_id and att.sheet_id.state not in ('draft', 'new'):
                raise UserError(_('You cannot modify an entry in a confirmed timesheet'))
        return True


class hr_timesheet_sheet_sheet_day(osv.osv):
    _name = "hr_timesheet_sheet.sheet.day"
    _description = "Timesheets by Period"
    _auto = False
    _order='name'
    _columns = {
        'name': fields.date('Date', readonly=True),
        'sheet_id': fields.many2one('hr_timesheet_sheet.sheet', 'Sheet', readonly=True, select="1"),
        'total_timesheet': fields.float('Total Timesheet', readonly=True),
        'total_attendance': fields.float('Attendance', readonly=True),
        'total_difference': fields.float('Difference', readonly=True),
    }
    _depends = {
        'account.analytic.line': ['date', 'unit_amount'],
        'hr.attendance': ['action', 'name', 'sheet_id'],
    }

    def init(self, cr):
        cr.execute("""create or replace view hr_timesheet_sheet_sheet_day as
            SELECT
                id,
                name,
                sheet_id,
                total_timesheet,
                total_attendance,
                cast(round(cast(total_attendance - total_timesheet as Numeric),2) as Double Precision) AS total_difference
            FROM
                ((
                    SELECT
                        MAX(id) as id,
                        name,
                        sheet_id,
                        timezone,
                        SUM(total_timesheet) as total_timesheet,
                        CASE WHEN SUM(orphan_attendances) != 0
                            THEN (SUM(total_attendance) +
                                CASE WHEN current_date <> name
                                    THEN 1440
                                    ELSE (EXTRACT(hour FROM current_time AT TIME ZONE 'UTC' AT TIME ZONE coalesce(timezone, 'UTC')) * 60) + EXTRACT(minute FROM current_time AT TIME ZONE 'UTC' AT TIME ZONE coalesce(timezone, 'UTC'))
                                END
                                )
                            ELSE SUM(total_attendance)
                        END /60  as total_attendance
                    FROM
                        ((
                            select
                                min(l.id) as id,
                                p.tz as timezone,
                                l.date::date as name,
                                s.id as sheet_id,
                                sum(l.unit_amount) as total_timesheet,
                                0 as orphan_attendances,
                                0.0 as total_attendance
                            from
                                account_analytic_line l
                                LEFT JOIN hr_timesheet_sheet_sheet s ON s.id = l.sheet_id
                                JOIN hr_employee e ON s.employee_id = e.id
                                JOIN resource_resource r ON e.resource_id = r.id
                                LEFT JOIN res_users u ON r.user_id = u.id
                                LEFT JOIN res_partner p ON u.partner_id = p.id
                            group by l.date::date, s.id, timezone
                        ) union (
                            select
                                -min(a.id) as id,
                                p.tz as timezone,
                                (a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC'))::date as name,
                                s.id as sheet_id,
                                0.0 as total_timesheet,
                                SUM(CASE WHEN a.action = 'sign_in' THEN -1 ELSE 1 END) as orphan_attendances,
                                SUM(((EXTRACT(hour FROM (a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC'))) * 60) + EXTRACT(minute FROM (a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC')))) * (CASE WHEN a.action = 'sign_in' THEN -1 ELSE 1 END)) as total_attendance
                            from
                                hr_attendance a
                                LEFT JOIN hr_timesheet_sheet_sheet s
                                ON s.id = a.sheet_id
                                JOIN hr_employee e
                                ON a.employee_id = e.id
                                JOIN resource_resource r
                                ON e.resource_id = r.id
                                LEFT JOIN res_users u
                                ON r.user_id = u.id
                                LEFT JOIN res_partner p
                                ON u.partner_id = p.id
                            WHERE action in ('sign_in', 'sign_out')
                            group by (a.name AT TIME ZONE 'UTC' AT TIME ZONE coalesce(p.tz, 'UTC'))::date, s.id, timezone
                        )) AS foo
                        GROUP BY name, sheet_id, timezone
                )) AS bar""")


class hr_timesheet_sheet_sheet_account(osv.osv):
    _name = "hr_timesheet_sheet.sheet.account"
    _description = "Timesheets by Period"
    _auto = False
    _order='name'
    _columns = {
        'name': fields.many2one('account.analytic.account', 'Project / Analytic Account', readonly=True),
        'sheet_id': fields.many2one('hr_timesheet_sheet.sheet', 'Sheet', readonly=True),
        'total': fields.float('Total Time', digits=(16,2), readonly=True),
        }

    _depends = {
        'account.analytic.line': ['account_id', 'date', 'unit_amount', 'user_id'],
        'hr_timesheet_sheet.sheet': ['date_from', 'date_to', 'user_id'],
    }

    def init(self, cr):
        cr.execute("""create or replace view hr_timesheet_sheet_sheet_account as (
            select
                min(l.id) as id,
                l.account_id as name,
                s.id as sheet_id,
                sum(l.unit_amount) as total
            from
                account_analytic_line l
                    LEFT JOIN hr_timesheet_sheet_sheet s
                        ON (s.date_to >= l.date
                            AND s.date_from <= l.date
                            AND s.user_id = l.user_id)
            group by l.account_id, s.id
        )""")




class res_company(osv.osv):
    _inherit = 'res.company'
    _columns = {
        'timesheet_range': fields.selection(
            [('day','Day'),('week','Week'),('month','Month')], 'Timesheet range',
            help="Periodicity on which you validate your timesheets."),
        'timesheet_max_difference': fields.float('Timesheet allowed difference(Hours)',
            help="Allowed difference in hours between the sign in/out and the timesheet " \
                 "computation for one sheet. Set this to 0 if you do not want any control."),
    }
    _defaults = {
        'timesheet_range': lambda *args: 'week',
        'timesheet_max_difference': lambda *args: 0.0
    }

class hr_employee(osv.osv):
    '''
    Employee
    '''

    _inherit = 'hr.employee'
    _description = 'Employee'

    def _timesheet_count(self, cr, uid, ids, field_name, arg, context=None):
        Sheet = self.pool['hr_timesheet_sheet.sheet']
        return {
            employee_id: Sheet.search_count(cr,uid, [('employee_id', '=', employee_id)], context=context)
            for employee_id in ids
        }

    _columns = {
        'timesheet_count': fields.function(_timesheet_count, type='integer', string='Timesheets'),
    }
