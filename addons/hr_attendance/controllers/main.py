from openerp import http, _
from openerp.http import request


class StockBarcodeController(http.Controller):

    @http.route('/hr_attendance/scan_from_main_menu', type='json', auth='user')
    def main_menu(self, barcode, **kw):
        """ Receive a barcode scanned from the main menu and return the appropriate
            action (change attendance of employee) or warning.
        """
        try_change_attendance = try_to_change_attendance(barcode)
        if try_change_attendance:
            return try_change_attendance

        return {'warning': _('No employee corresponding to barcode %(barcode)s') % {'barcode': barcode}}


def try_to_change_attendance(barcode):
    """ If barcode represents an employee, check him in or out
    """
    corresponding_employee = request.env['hr.employee'].search([('barcode', '=', barcode)], limit=1)
    if corresponding_employee:
        employee_check = corresponding_employee.attendance_action_change()
        if employee_check == "checked in":
            action_welcome_message = request.env.ref('hr_attendance.hr_attendance_action_welcome_message')
            action_welcome_message = action_welcome_message.read()[0]
            action_welcome_message['res_id'] = corresponding_employee.id
            return {'action': action_welcome_message}
        elif employee_check == "checked out":
            action_welcome_message = request.env.ref('hr_attendance.hr_attendance_action_farewell_message')
            action_welcome_message = action_welcome_message.read()[0]
            action_welcome_message['res_id'] = corresponding_employee.id
            return {'action': action_welcome_message}

    return False
