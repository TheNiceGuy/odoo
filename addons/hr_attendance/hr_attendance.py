# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import random
from datetime import datetime

from openerp import models, fields, api, exceptions, _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class hr_attendance(models.Model):
    _name = "hr.attendance"
    _description = "Attendance"

    def _default_employee(self):
        ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
        return ids and ids[0] or False

    def _default_check_in(self):
        return fields.Datetime.now()

    employee_id = fields.Many2one('hr.employee', string="Employee", default=_default_employee, required=True, select=True)  # ondelete='cascade' ?
    department_id = fields.Many2one('hr.department', string="Department", related="employee_id.department_id")
    check_in = fields.Datetime(string="Check In", default=_default_check_in, required=True)  # default doesn't get updated ? how come ???
    check_out = fields.Datetime(string="Check Out")
    worked_hours = fields.Float(string='Worked Hours', compute='_get_worked_hours', store=True, readonly=True)

    @api.depends('check_in', 'check_out')
    def _get_worked_hours(self):
        for record in self:
            if not record.check_in or not record.check_out:
                {}
            else:
                delta = datetime.strptime(record.check_out, DEFAULT_SERVER_DATETIME_FORMAT) - datetime.strptime(
                    record.check_in, DEFAULT_SERVER_DATETIME_FORMAT)    # il y avait fields.Datetime.to_string/from_string :/
                record.worked_hours = delta.total_seconds() / 3600.0

        # self.env['hr.employee'].search(()) self.env.user_id.id # this doesn't work? do I have to go through a fct for the default?

    @api.constrains('check_in', 'check_out')  # api.contrains ou _sql_constraints with domains ? what's the difference ?
    def _verify_check_in_check_out(self):
        for record in self:
            if record.check_in and record.check_out:
                if record.check_out < record.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))

    @api.multi
    @api.constrains('check_out', 'check_in', 'employee_id')
    def _verify_validity(self):
        """ Verifies the validity of the attendance record.
            - record check_in must be before check_out
            - for the same employee we must     have :
                * maximum 1 "open" record (without check_out)
                * no overlapping time slices with previous employee records
        """
        # import ipdb
        # ipdb.set_trace()
        for record in self:
            if not record.check_out:
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', record.employee_id.id)]):
                    if same_employee_record == record:
                        continue
                    if not same_employee_record.check_out: # we can't create a record without check out time if one already exist for that employee
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee hasn't checked out since {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                            same_employee_record.check_in))
                    #check if R_check_in is contained in SER
                    if same_employee_record.check_in < record.check_in and record.check_in < same_employee_record.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(record.check_in)))))
            else:
                if record.check_out < record.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', record.employee_id.id)]):
                    if same_employee_record == record:
                        continue
                    #check if SER_check_in is contained in R
                    if record.check_in < same_employee_record.check_in and same_employee_record.check_in < record.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_in)))))
                    if same_employee_record.check_out:
                        #check if R_check_in is contained in SER
                        if same_employee_record.check_in < record.check_in and record.check_in < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(record.check_in)))))
                        #check if SER_check_out is contained in R
                        if record.check_in < same_employee_record.check_out and same_employee_record.check_out < record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_out)))))
                        #check if R_check_out is contained in SER
                        if same_employee_record.check_in < record.check_out and record.check_out < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', record.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(record.check_out)))))


class hr_employee(models.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    state = fields.Selection(string="Attendance", compute='_get_state', selection=[('absent', "Absent"), ('present', "Present")])
    barcode = fields.Char(string="Badge ID", help="ID used for employee identification.", copy=False)
    pin_number = fields.Char(string="Pin Number", default='_generate_random_pin', help="Pin number used for checking in and out.")
    last_check = fields.Datetime(string="Last Check In/Out", compute='_get_last_check')

    attendance_access = fields.Boolean(string='Attendance Access', compute='_attendance_access')

    @api.constrains('barcode')
    def _verify_barcode(self):
        for record in self:
            if len(record.barcode) != 13:
                raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 cyphers."))
            try:
                int(record.barcode)
            except ValueError:
                raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 cyphers."))
            for other_record in self.env['hr.employee']:
                if record == other_record:
                    continue
                if record.barcode == other_record.barcode:
                    raise exceptions.ValidationError(_("The Badge ID must be unique, this one is already assigned to another employee."))
            # should it also start with a certain sequence ??? to not have a possible duplicate with other barcode products ?

    @api.constrains('pin_number')
    def _verify_pin(self):
        for record in self:
            if len(record.pin_number) != 4:
                raise exceptions.ValidationError(_("The pin number must be a sequence of 4 cyphers."))
            try:
                int(record.barcode)
            except ValueError:
                raise exceptions.ValidationError(_("The pin number must be a sequence of 4 cyphers."))

    @api.multi
    def _generate_random_pin(self):
        for record in self:
            pin = ""
            for i in range(4):
                pin = pin + random.randint(0, 9)
            record.pin_number = pin

    @api.multi
    def _get_last_check(self):
        for record in self:
            record.last_check = None
            for attendance_record in self.env['hr.attendance'].search([('employee_id', '=', record.id)]):
                if attendance_record.check_out:
                    if record.last_check:
                        if record.last_check < attendance_record.check_out:
                            record.last_check = attendance_record.check_out
                    else:
                        record.last_check = attendance_record.check_out
                else:
                    if record.last_check:
                        if record.last_check < attendance_record.check_in:
                            record.last_check = attendance_record.check_in
                    else:
                        record.last_check = attendance_record.check_in

    @api.multi
    def _get_state(self):
        # we mark 'present' those who have an open attendance record (without check out time)
        # the others are marked 'absent'
        for record in self:
            record.state = 'absent'
            for attendance_record in self.env['hr.attendance'].search([('employee_id', '=', record.id)]):
                # can I reverse the search results ? to have them by decreasing ids (~decreasing create date)
                if not attendance_record.check_out:
                    record.state = 'present'
                    break

    @api.multi
    # def _attendance_access(self, cr, uid, ids, name, args, context=None):
    def _attendance_access(self):
        # this function field use to hide attendance button to singin/singout from menu
        # visible = self.pool.get("res.users").has_group(cr, uid, "base.group_hr_attendance")
        visible = []
        for record in self:
            visible[record.id] = record.id.has_group("base.group_hr_attendance")  # or self.uid
        return dict(visible)

    @api.multi
    def attendance_action_change(self): # , cr, uid, ids, context=None):
        return# if context is None:
        #     context = {}
        # action_date = context.get('action_date', False)
        # action = context.get('action', False)
        # hr_attendance = self.pool.get('hr.attendance')
        # warning_sign = {'sign_in': _('Sign In'), 'sign_out': _('Sign Out')}
        # for employee in self.browse(cr, uid, ids, context=context):
        #     if not action:
        #         if employee.state == 'present': action = 'sign_out'
        #         if employee.state == 'absent': action = 'sign_in'

        #     if not self._action_check(cr, uid, employee.id, action_date, context):
        #         raise UserError(_('You tried to %s with a date anterior to another event !\nTry to contact the HR Manager to correct attendances.') % (warning_sign[action],))

        #     vals = {'action': action, 'employee_id': employee.id}
        #     if action_date:
        #         vals['name'] = action_date
        #     hr_attendance.create(cr, uid, vals, context=context)
        # return True
