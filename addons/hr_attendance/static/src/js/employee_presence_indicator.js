odoo.define('hr_attendance.kanban_presence_indicator', function (require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');
var Session = require('web.session');
var BarcodeHandlerMixin = require('barcodes.BarcodeHandlerMixin');
var QWeb = core.qweb;

var kanban_widgets = require('web_kanban.widgets');

var _t = core._t;

var FieldPresenceIndicator = kanban_widgets.AbstractField.extend({
    init: function() {
        this._super.apply(this, arguments);
    },
    start: function() {
        this.display_field();
        this.render_value();
        return this._super();
    },
    render_value: function() {
        if(this.field.raw_value == 'present'){
            this.$('.o_attendance_field_presence_indicator').css("background-color", "#00FF00");
        } else {
            this.$('.o_attendance_field_presence_indicator').css("background-color", "#FF0000");
        }
        
    },
    display_field: function() {
        this.$el.html(QWeb.render("FieldPresenceIndicator"));
    },
});

kanban_widgets.registry.add('presence_indicator', FieldPresenceIndicator);

});