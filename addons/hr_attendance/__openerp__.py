# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Attendances',
    'version': '1.1',
    'category': 'Human Resources',
    'description': """
This module aims to manage employee's attendances.
==================================================

Keeps account of the attendances of the employees on the basis of the
actions(Sign in/Sign out) performed by them.
       """,
    'website': 'https://www.odoo.com/page/employees',
    'depends': ['hr', 'report', 'barcodes'], # web?
    'data': [
        'security/hr_attendance_security.xml',
        'security/ir.model.access.csv',
        'views/web_asset_backend_template.xml',
        'views/hr_attendance_view.xml',
        # 'report/hr_attendance_report.xml',
        # 'wizard/hr_attendance_error_view.xml',
        'wizard/hr_attendance_pin_pad_view.xml',
        # 'wizard/hr_employee_badge.xml',
        # 'report/report_attendance_errors.xml',
        'views/hr_dashboard.xml',
        'views/employee_view.xml',
        'views/res_config_view.xml',
    ],
    'demo': [
        'data/hr_attendance_demo.xml'
    ],
    'test': [
        # 'test/attendance_process.yml',
        # 'test/hr_attendance_report.yml',
    ],
    'installable': True,
    'auto_install': False,
    #web
    'qweb': [
        "static/src/xml/attendance.xml",
    ],
}
