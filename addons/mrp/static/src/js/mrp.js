odoo.define('mrp.mrp_state', function (require) {

var core = require('web.core');
var common = require('web.form_common');


var SetBulletStatus = common.AbstractField.extend(common.ReinitializeFieldMixin,{
    init: function(field_manager, node) {
        this._super(field_manager, node);
        this.classes = this.options && this.options.classes || {};
    },
    render_value: function() {
        this._super.apply(this, arguments);
        if (this.get("effective_readonly")) {
            var bullet_class = this.classes[this.get('value')] || 'default';
            this.$el
                .removeClass('text-success text-danger text-default')
                .addClass('fa fa-circle text-' + bullet_class);
        }
    },
});

core.form_widget_registry.add('bullet_state', SetBulletStatus);
});
