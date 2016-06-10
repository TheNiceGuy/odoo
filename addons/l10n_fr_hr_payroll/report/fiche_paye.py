# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class FichePayeParser(models.AbstractModel):
    _name = 'report.l10n_fr_hr_payroll.report_l10nfrfichepaye'

    def get_payslip_lines(self, objs):
        res = []
        ids = []
        for item in objs:
            if item.appears_on_payslip == True and not item.salary_rule_id.parent_rule_id :
                ids.append(item.id)
        if ids:
            res = self.env['hr.payslip.line'].browse(ids)
        return res

    def get_total_by_rule_category(self, obj, code):
        category_total = 0
        cate_ids = self.env['hr.salary.rule.category'].search([('code', '=', code)], limit=1)
        if cate_ids:
            line_ids = self.env['hr.payslip.line'].search([('slip_id', '=', obj.id), ('category_id.id', '=', cate_ids.id)])
            for line in line_ids:
                category_total += line.total
        return category_total

    def get_employer_line(self, obj, parent_line):
        return self.env['hr.payslip.line'].search([('slip_id', '=', obj.id), ('salary_rule_id.parent_rule_id.id', '=', parent_line.salary_rule_id.id)], limit=1)

    @api.multi
    def render_html(self, data):
        payslip = self.env['hr.payslip'].browse(self.ids)
        docargs = {
            'doc_ids': self.ids,
            'doc_model': 'hr.payslip',
            'data': data,
            'docs': payslip,
            'lang': "fr_FR",
            'get_payslip_lines': self.get_payslip_lines,
            'get_total_by_rule_category': self.get_total_by_rule_category,
            'get_employer_line': self.get_employer_line,
        }
        return self.env['report'].render('l10n_fr_hr_payroll.report_l10nfrfichepaye', docargs)
