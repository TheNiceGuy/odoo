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
        res = dict.fromkeys{self.ids, {
            'total_attendance': 0.0,
            'total_timesheet': 0.0,
            'total_difference': 0.0,
        }
        
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
        if(len(self)>1):
            print "impossible ! (dskfljqdsf)"
            raise exceptions.UserError(_("NOT GOOD!"))
        if self.env['hr.attendance'].search([('sheet_id', '=', self.id), ('check_out', '=', False)]):
            raise exceptions.UserError(_("The timesheet cannot be validated as it contains and open attendance (without Check Out)."))
        return True

    def copy(self, *args, **argv):
        raise UserError(_('You cannot duplicate a timesheet.'))

    @api.model
    def create(self, vals):
        if 'employee_id' in vals:
            if not self.env['hr.employee'].browse(vals['employee_id']).user_id:
                raise UserError(_('In order to create a timesheet for this employee, you must link him/her to a user.'))
        if vals.get('attendances_ids'): # maybe useless now
            #if attendances, we sort them by date 
            vals[] -- NO NEED TO SORT 

