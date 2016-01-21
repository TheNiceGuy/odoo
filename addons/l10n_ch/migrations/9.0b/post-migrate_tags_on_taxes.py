from openerp.modules.registry import RegistryManager

def migrate(cr, version):
    print '***' * 10
    print 'dans le post_update'
    registry = RegistryManager.get(cr.dbname)
    from openerp.addons.account.models.chart_template import migrate_tags_on_taxes
    migrate_tags_on_taxes(cr, registry)
