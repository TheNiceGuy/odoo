# -*- coding: utf-8 -*-

from urlparse import urlsplit
from openerp import api, fields, models


class MaintenanceConfigSettings(models.TransientModel):
    _name = 'maintenance.config.settings'
    _inherit = 'res.config.settings'

    maintenance_alias_prefix = fields.Char('Use the following alias to report internal maintenance issue')
    alias_domain = fields.Char("Alias Domain")

    @api.multi
    def get_default_alias_maintenance(self):
        alias_name = False
        alias_id = self.env.ref('maintenance.mail_alias_equipment')
        if alias_id:
            alias_name = alias_id.alias_name
        return {'maintenance_alias_prefix': alias_name}

    @api.multi
    def set_default_alias_maintenance(self):
        for record in self:
            default_maintenance_alias_prefix = record.get_default_alias_maintenance()['maintenance_alias_prefix']
            if record.maintenance_alias_prefix != default_maintenance_alias_prefix:
                alias_id = self.env.ref('maintenance.mail_alias_equipment')
                if alias_id:
                    alias_id.write({'alias_name': record.maintenance_alias_prefix})
        return True

    @api.multi
    def get_default_alias_domain(self):
        alias_domain = self.env['ir.config_parameter'].get_param("mail.catchall.domain")
        if not alias_domain:
            domain = self.env["ir.config_parameter"].get_param("web.base.url")
            try:
                alias_domain = urlsplit(domain).netloc.split(':')[0]
            except Exception:
                pass
        return {'alias_domain': alias_domain}
