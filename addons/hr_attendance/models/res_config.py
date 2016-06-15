# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class BaseConfigSettings(models.TransientModel):
    # _name = 'attendance.config.settings'
    _inherit = 'base.config.settings'

    attendance_use_employee_pin = fields.Selection([('False', "No"), ('True', "Yes")],
        string='check in using PIN', help='Employees must enter their PIN to check in and out.')

    @api.model
    def get_default_auth_signup_template_user_id(self, fields):
        IrConfigParam = self.env['ir.config_parameter']
        return {
            'attendance_use_employee_pin': IrConfigParam.get_param('attendance_use_employee_pin', 'False'),
        }

    @api.multi
    def set_auth_signup_template_user_id(self):
        self.ensure_one()
        IrConfigParam = self.env['ir.config_parameter']
        IrConfigParam.set_param('attendance_use_employee_pin', self.attendance_use_employee_pin)
