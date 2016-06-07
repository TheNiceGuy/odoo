# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrAttendancePinPad(models.TransientModel):
    _name = 'hr_attendance.pin_pad'

    def _default_employee(self):
        return self.env['hr.employee'].browse(self._context.get('employee_id'))

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, default=_default_employee)
    entered_pin = fields.Char(string="PIN", help="PIN used for checking in and out, contact HR if forgotten.")

    @api.multi
    def verify_pin_change_attendance(self):
        if self.entered_pin == self.employee_id.pin:
            employee_check = self.employee_id.attendance_action_change()
            if employee_check == "checked in":
                return {
                    'name': 'Attendance',
                    'type': 'ir.actions.client',
                    'tag': 'hr_attendance_welcome_message',
                    'res_id': self.employee_id.id,
                    'options': {
                        'clear_breadcrumbs': True,
                    }
                }
            elif employee_check == "checked out":
                return {
                    'name': 'Attendance',
                    'type': 'ir.actions.client',
                    'tag': 'hr_attendance_farewell_message',
                    'res_id': self.employee_id.id,
                    'options': {
                        'clear_breadcrumbs': True,
                    }
                }
        else:
            raise UserError(_('Wrong PIN.')) # should we implement a limited number of tries (in a certain amount of time) ?
