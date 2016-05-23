# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import random
from datetime import datetime

from openerp import models, fields, api, exceptions, _
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class hr_attendance(models.Model):
    _name = "hr.attendance"
    _description = "Attendance"
    _order = "check_in desc"

    def _default_employee(self):
        ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
        return ids and ids[0] or False

    def _default_check_in(self):
        return fields.Datetime.now()

    @api.multi
    def write(self, vals):
        import ipdb
        ipdb.set_trace()
        return super(hr_attendance, self).write(vals)

    employee_id = fields.Many2one('hr.employee', string="Employee", default=_default_employee, required=True, select=True)  # ondelete='cascade' ?
    department_id = fields.Many2one('hr.department', string="Department", related="employee_id.department_id")
    check_in = fields.Datetime(string="Check In", default=_default_check_in, required=True)  # default doesn't get updated ? how come ???
    check_out = fields.Datetime(string="Check Out")
    worked_hours = fields.Float(string='Worked Hours', compute='_get_worked_hours', store=True, readonly=True)

    @api.depends('check_in', 'check_out')
    def _get_worked_hours(self):
        for attendance in self:
            if not attendance.check_in or not attendance.check_out:
                {}
            else:
                delta = datetime.strptime(attendance.check_out, DEFAULT_SERVER_DATETIME_FORMAT) - datetime.strptime(
                    attendance.check_in, DEFAULT_SERVER_DATETIME_FORMAT)    # il y avait fields.Datetime.to_string/from_string :/
                attendance.worked_hours = delta.total_seconds() / 3600.0

        # self.env['hr.employee'].search(()) self.env.user_id.id # this doesn't work? do I have to go through a fct for the default?

    @api.constrains('check_in', 'check_out')  # api.contrains ou _sql_constraints with domains ? what's the difference ?
    def _verify_check_in_check_out(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                if attendance.check_out < attendance.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))

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
        for attendance in self:
            if not attendance.check_out:
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', attendance.employee_id.id)]):
                    if same_employee_record == attendance:
                        continue
                    if not same_employee_record.check_out: # we can't create a record without check out time if one already exist for that employee
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee hasn't checked out since {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                            same_employee_record.check_in))
                    #check if R_check_in is contained in SER
                    if same_employee_record.check_in < attendance.check_in and attendance.check_in < same_employee_record.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in)))))
            else:
                if attendance.check_out < attendance.check_in:
                    raise exceptions.ValidationError(_("\"Check Out\" time cannot be earlier than \"Check In\" time."))
                for same_employee_record in self.env['hr.attendance'].search([('employee_id', '=', attendance.employee_id.id)]):
                    if same_employee_record == attendance:
                        continue
                    #check if SER_check_in is contained in R
                    if attendance.check_in < same_employee_record.check_in and same_employee_record.check_in < attendance.check_out:
                        raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                            self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_in)))))
                    if same_employee_record.check_out:
                        #check if R_check_in is contained in SER
                        if same_employee_record.check_in < attendance.check_in and attendance.check_in < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_in)))))
                        #check if SER_check_out is contained in R
                        if attendance.check_in < same_employee_record.check_out and same_employee_record.check_out < attendance.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(same_employee_record.check_out)))))
                        #check if R_check_out is contained in SER
                        if same_employee_record.check_in < attendance.check_out and attendance.check_out < same_employee_record.check_out:
                            raise exceptions.ValidationError(_("Cannot create new attendance record for {0}, the employee was already present on {1}").format(
                                self.env['hr.employee'].search([('user_id', '=', attendance.employee_id.id)]).name_related,
                                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.from_string(attendance.check_out)))))


class hr_employee(models.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    def _generate_random_pin(self):
        pin = 0
        for i in range(4):
            pin = pin + random.randint(0, 9) * 10**i
        return str(pin)

    state = fields.Selection(string="Attendance", compute='_get_state', selection=[('absent', "Absent"), ('present', "Present")], copy=False)
    barcode = fields.Char(string="Badge ID", help="ID used for employee identification.", copy=False)
    pin = fields.Char(string="PIN", default=_generate_random_pin, help="PIN used for Check In/Out in Attendance.", copy=False)
    last_check = fields.Datetime(string="Last Check In/Out", compute='_get_last_check', copy=False)
    attendance_ids = fields.One2many('hr.attendance', 'employee_id', help='list of attendances for the employee')

    attendance_access = fields.Boolean(string='Attendance Access', compute='_attendance_access')

    _sql_constraints = [('barcode_uniq', 'unique (barcode)', "The Badge ID must be unique, this one is already assigned to another employee.")]

    @api.constrains('barcode')
    def _verify_barcode(self):
        for employee in self:
            if employee.barcode:
                if len(employee.barcode) != 13:
                    raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 cyphers."))
                try:
                    int(employee.barcode)
                except ValueError:
                    raise exceptions.ValidationError(_("The Badge ID must be a sequence of 13 cyphers."))

    @api.constrains('pin')
    def _verify_pin(self):
        for employee in self:
            if employee.pin:
                if len(employee.pin) != 4:
                    raise exceptions.ValidationError(_("The PIN must be a sequence of 4 cyphers."))
                try:
                    int(employee.pin)
                except ValueError:
                    raise exceptions.ValidationError(_("The PIN must be a sequence of 4 cyphers."))

    @api.depends('attendance_ids.check_in', 'attendance_ids.check_out')
    def _get_last_check(self):
        """ We take the latest employee check in/out Datetime
        """
        for employee in self:
            employee.last_check = None
            employee_records = employee.attendance_ids.sorted(reverse=True)
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
            # which is faster ?
            # if len(self.env['hr.attendance'].search([('employee_id', '=', record.id), ('check_in', '<', now), '|', ('check_out', '=', False), ('check_out', '>', now)])):
            #     record.state = 'present'

    @api.multi
    def _attendance_access(self):
        """ this function field is used to hide attendance button to singin/singout from menu
        """
        visible = self.env['res.users'].has_group("base.group_hr_attendance")
        return dict([(employee.id, visible) for employee in self])

    @api.multi
    def attendance_action_change(self): # , cr, uid, ids, context=None):
        """ Check In/Check Out action
            Check In : create a new attendance record
            Check Out : modify check_out field of appropriate attendance record
        """
        action_date = self.env.context.get('action_date', False) # action_date est bien une variable définie par l'execution de l'action ?
        action = self.env.context.get('action', False)
        for employee in self:
            if not action:
                if employee.state == 'present':
                    action = 'sign_out'
                if employee.state == 'absent':
                    action = 'sign_in'
            else:
                if employee.state == 'present' and action != 'sign_out':
                    raise exceptions.UserError(_('You tried to Check In while you are marked as Present !\nTry to contact the HR Manager to correct attendances.'))
                if employee.state == 'absent' and action != 'sign_in':
                    raise exceptions.UserError(_('You tried to Check Out while you are marked as Absent !\nTry to contact the HR Manager to correct attendances.'))

            if action == 'sign_in':
                vals = {'employee_id': employee.id}
                department_id = employee.department_id
                if department_id:
                    vals['department_id'] = department_id
                if action_date:
                    vals['check_in'] = action_date
                self.env['hr.attendance'].create(vals)
            else:
                attendance_report = self.env['hr.attendance'].search([('employee_id', '=', employee.id)], order='check_in desc', limit=1)
                if attendance_report:
                    if not action_date:
                        action_date = fields.Datetime.now()
                    attendance_report.check_out = action_date
        return True
