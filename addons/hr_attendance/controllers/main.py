from openerp import http, _
from openerp.http import request


class HrAttendanceController(http.Controller):

    @http.route('/hr_attendance/scan_from_main_menu', type='json', auth='user')
    def scan_from_main_menu(self, barcode, **kw):
        """ Receive a barcode scanned from the main menu and return the appropriate
            action (change attendance of employee) or warning.
        """
        corresponding_employee = request.env['hr.employee'].search([('barcode', '=', barcode)], limit=1)
        try_change_attendance = self.try_to_change_attendance(corresponding_employee, 'hr_attendance.hr_attendance_action_main_menu')
        if try_change_attendance:
            return try_change_attendance

        return {'warning': _('No employee corresponding to barcode %(barcode)s') % {'barcode': barcode}}

    @http.route('/hr_attendance/basic_change_attendance', type='json', auth='user')
    def basic_change_attendance(self, employee_id, **kw):
        """ Basic employee performs a check in or out.
        """
        corresponding_employee = request.env['hr.employee'].search([('id', '=', employee_id)])
        try_change_attendance = self.try_to_change_attendance(corresponding_employee, 'hr_attendance.hr_attendance_action_basic_employee_main_menu')
        if try_change_attendance:
            return try_change_attendance

        return {'warning': _('No employee corresponding to id %(employee_id)s') % {'employee_id': employee_id}}

    def try_to_change_attendance(self, employee, next_action):
        """ Change the attendance of employee (perform a check in or check out)
        """
        if employee:
            if employee.user_id:
                employee_check = employee.sudo(employee.user_id.id).attendance_action_change()
            else:
                employee_check = employee.sudo().attendance_action_change()
            # employee_check = employee.attendance_action_change()
            if employee_check == "checked in":
                action_welcome_message = request.env.ref('hr_attendance.hr_attendance_action_welcome_message')
                action_welcome_message = action_welcome_message.read()[0]
                action_welcome_message['res_id'] = employee.id
                action_welcome_message['next_action'] = next_action
                return {'action': action_welcome_message}
            elif employee_check == "checked out":
                action_welcome_message = request.env.ref('hr_attendance.hr_attendance_action_farewell_message')
                action_welcome_message = action_welcome_message.read()[0]
                action_welcome_message['res_id'] = employee.id
                action_welcome_message['next_action'] = next_action
                return {'action': action_welcome_message}

        return False
