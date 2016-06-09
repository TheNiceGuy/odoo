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
        employee = self.employee_id
        if self.entered_pin == employee.pin:
            self.unlink()
            if employee.user_id:
                employee_check = employee.sudo(employee.user_id.id).attendance_action_change()
            else:
                employee_check = employee.sudo().attendance_action_change()
            action = {
                'name': 'Attendance',
                'type': 'ir.actions.client',
                'res_id': employee.id,
                'options': {
                    'clear_breadcrumbs': True,
                }
            }
            if employee_check == "checked in":
                action['tag'] = 'hr_attendance_welcome_message'
                return action
            elif employee_check == "checked out":
                action['tag'] = 'hr_attendance_farewell_message'
                return action
        else:
            raise UserError(_('Wrong PIN.')) # should we implement a limited number of tries (in a certain amount of time) ?
