# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime

from odoo import models, fields, api, exceptions, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class HrAttendance(models.Model):
    _name = "hr.attendance"
    _description = "Attendance"
    _order = "check_in desc"

    def _default_employee(self):
        return self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)

    @api.multi
    def write(self, vals):
        # import ipdb; ipdb.set_trace()
        return super(HrAttendance, self).write(vals)

    employee_id = fields.Many2one('hr.employee', string="Employee", default=_default_employee, required=True, ondelete='cascade', index=True)
    department_id = fields.Many2one('hr.department', string="Department", related="employee_id.department_id")
    check_in = fields.Datetime(string="Check In", default=fields.Datetime.now, required=True)
    check_out = fields.Datetime(string="Check Out")
    worked_hours = fields.Float(string='Worked Hours', compute='_compute_worked_hours', store=True, readonly=True)

    @api.multi
    def name_get(self):
        result = []
        for attendance in self:
            result.append((self.id, "attendance : check in at " + self.check_in))
        return result

    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for attendance in self:
            if not attendance.check_in or not attendance.check_out:
                {}
            else:
                delta = datetime.strptime(attendance.check_out, DEFAULT_SERVER_DATETIME_FORMAT) - datetime.strptime(
                    attendance.check_in, DEFAULT_SERVER_DATETIME_FORMAT)
                attendance.worked_hours = delta.total_seconds() / 3600.0

    @api.constrains('check_in', 'check_out')
    def _check_check_in_check_out(self):
        """ verifies if check_in is earlier than check_out. """
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                if attendance.check_out < attendance.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))

    @api.constrains('check_out', 'check_in', 'employee_id')
    def _check_validity(self):
        """ Verifies the validity of the attendance record compared to the others from the same employee.
            For the same employee we must have :
                * maximum 1 "open" record (without check_out)
                * no overlapping time slices with previous employee records
        """
        for attendance in self:
            if not attendance.check_out:
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', attendance.employee_id.id)]):
                    if same_employee_record == attendance:
                        continue
                    # we can't have another record without check out time if one already exist for that employee
                    if not same_employee_record.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee hasn't checked out since {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                            same_employee_record.check_in))
                    # check if A_check_in is contained in SER
                    if same_employee_record.check_in < attendance.check_in and attendance.check_in < same_employee_record.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in)))))
            else:
                if attendance.check_out < attendance.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', attendance.employee_id.id)]):
                    if same_employee_record == attendance:
                        continue
                    #check if SER_check_in is contained in A
                    if attendance.check_in < same_employee_record.check_in and same_employee_record.check_in < attendance.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_in)))))
                    if same_employee_record.check_out:
                        #check if A_check_in is contained in SER
                        if same_employee_record.check_in < attendance.check_in and attendance.check_in < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in)))))
                        #check if SER_check_out is contained in A
                        if attendance.check_in < same_employee_record.check_out and same_employee_record.check_out < attendance.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_out)))))
                        #check if A_check_out is contained in SER
                        if same_employee_record.check_in < attendance.check_out and attendance.check_out < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.user_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_out)))))
