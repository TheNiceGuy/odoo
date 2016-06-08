# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import choice
from string import digits

from odoo import models, fields, api, exceptions, _


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    def _default_random_pin(self):
        return ("".join(choice(digits) for i in range(4)))

    def _default_random_barcode(self):
        barcode = None
        while not barcode or any(self.env['hr.employee'].search([('barcode', '=', barcode), ('id', '!=', self.id)])):
            barcode = "".join(choice(digits) for i in range(13))
        return barcode

    state = fields.Selection(string="Attendance", compute='_get_state', selection=[('absent', "Absent"), ('present', "Present")])
    barcode = fields.Char(string="Badge ID", help="ID used for employee identification.", default=_default_random_barcode, copy=False)
    pin = fields.Char(string="PIN", default=_default_random_pin, help="PIN used for Check In/Out in Attendance.", copy=False)
    last_check = fields.Datetime(string="Last Check In/Out", compute='_compute_last_check', copy=False)
    attendance_ids = fields.One2many('hr.attendance', 'employee_id', help='list of attendances for the employee')

    attendance_access = fields.Boolean(string='Attendance Access', compute='_compute_attendance_access', help='Used to hide or reveal the Check In/Out button from menu(top right).')

    _sql_constraints = [('barcode_uniq', 'unique (barcode)', "The Badge ID must be unique, this one is already assigned to another employee.")]

    @api.depends('attendance_ids.check_in', 'attendance_ids.check_out', 'attendance_ids')
    def _compute_last_check(self):
        """ We take the latest employee check in/out Datetime
        """
        for employee in self:
            employee.last_check = None
            employee_records = employee.attendance_ids.sorted(key='check_in', reverse=True)
            if any(employee_records):
                employee.last_check = employee_records[0].check_out or employee_records[0].check_in

    @api.depends('attendance_ids.check_in', 'attendance_ids.check_out')
    def _get_state(self):
        """ We mark 'present' those who have an open attendance record (without check out time)
            the others are marked 'absent'
        """
        for employee in self:
            employee.state = 'absent'
            now = fields.Datetime.now()

            if any(employee.attendance_ids.filtered(lambda a: a.check_in <= now and (a.check_out is False or a.check_out > now))):
                employee.state = 'present'

    def _compute_attendance_access(self):
        """ this function field is used to hide attendance button to singin/singout from menu
        """
        self.attendance_access = self.env['res.users'].has_group("base.group_hr_attendances_manual")

    @api.constrains('barcode')
    def _verify_barcode(self):
        for employee in self:
            if employee.barcode:
                # temporarily commented to perform manual barcode tests
                # if len(employee.barcode) != 13:
                #     raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 digits."))
                try:
                    int(employee.barcode)
                except ValueError:
                    raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 digits."))

    @api.constrains('pin')
    def _verify_pin(self):
        for employee in self:
            if employee.pin:
                if len(employee.pin) != 4:
                    raise exceptions.ValidationError(_("The PIN must be a sequence of 4 digits."))
                try:
                    int(employee.pin)
                except ValueError:
                    raise exceptions.ValidationError(_("The PIN must be a sequence of 4 digits."))

    @api.multi
    def attendance_action_change(self):
        """ Check In/Check Out action
            Check In : create a new attendance record
            Check Out : modify check_out field of appropriate attendance record
        """
        if len(self) > 1:
            raise exceptions.UserError(_('Cannot perform check in or check out on multiple employees.'))
        action_date = fields.Datetime.now()

        action = 'sign_in'
        if self.state == 'present':
            action = 'sign_out'

        if action == 'sign_in':
            vals = {'employee_id': self.id}
            department_id = self.department_id
            if department_id:
                vals['department_id'] = department_id
            if action_date:
                vals['check_in'] = action_date
            self.env['hr.attendance'].create(vals)
            return "checked in"
        else:
            attendance_report = self.env['hr.attendance'].search([('employee_id', '=', self.id), ('check_out', '=', False)], limit=1)
            if attendance_report:
                attendance_report.check_out = action_date
            else:
                raise exceptions.UserError(_('Cannot perform check out on %s, could not find corresponding check in.'))
            return "checked out"

    @api.model
    def get_company_name(self):
        """ called from js to get company name (to get rif of and implement in js properly)
        """
        company = self.env['res.users'].browse([self._uid]).company_id
        return {"company_name": company.name,
                "company_logo": company.logo}
