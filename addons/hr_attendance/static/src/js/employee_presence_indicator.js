odoo.define('hr_attendance.kanban_presence_indicator', function (require) {
"use strict";

var core = require('web.core');
var kanban_widgets = require('web_kanban.widgets');

var QWeb = core.qweb;
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
            this.$('.o_hr_attendance_field_presence_indicator').css("background-color", "#00FF00");
        } else {
            this.$('.o_hr_attendance_field_presence_indicator').css("background-color", "#FF0000");
        }
        
    },
    display_field: function() {
        this.$el.html(QWeb.render("FieldPresenceIndicator"));
    },
});

kanban_widgets.registry.add('presence_indicator', FieldPresenceIndicator); // add hr_attendance_

});