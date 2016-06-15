# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class HrAttendancePinPad(models.TransientModel):
    _name = 'hr_attendance.pin_pad'

    def _default_employee(self):
        return self.env['hr.employee'].browse(self._context.get('employee_id'))

    def _default_employee_name(self):
        # import ipdb;ipdb.set_trace()
        return self._default_employee().name

    def _default_use_pin(self):
        return safe_eval(self.env['ir.config_parameter'].get_param('attendance_use_employee_pin'))

    def _default_employee_present(self):
        return self._default_employee().state == 'present'

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, default=_default_employee, readonly=True)
    employee_name = fields.Char(default=_default_employee_name, string="Employee name", readonly=True)
    employee_present = fields.Boolean(default=_default_employee_present, readonly=True)
    use_pin = fields.Boolean(default=_default_use_pin, readonly=True)
    entered_pin = fields.Char(string="PIN")

    @api.multi
    def verify_pin_change_attendance(self):
        employee = self.employee_id
        if self.entered_pin == employee.pin or not self.use_pin:
            self.unlink()
            if employee.user_id:
                employee_check = employee.sudo(employee.user_id.id).attendance_action_change()
            else:
                employee_check = employee.sudo().attendance_action_change()
            action = {
                'name': 'Attendance',
                'type': 'ir.actions.client',
                'res_id': employee.id,
                'next_action': 'hr_attendance.hr_attendance_action_main_menu',
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
