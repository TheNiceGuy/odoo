odoo.define('hr_attendance.pin_pad', function (require) {
"use strict";

var core = require('web.core');
var form_common = require('web.form_common');

var QWeb = core.qweb;
var _t = core._t;

var PinPad = form_common.AbstractField.extend({
    events: {
        'click .o_hr_attendance_pin_pad_button_0': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 0); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_1': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 1); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_2': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 2); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_3': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 3); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_4': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 4); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_5': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 5); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_6': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 6); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_7': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 7); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_8': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 8); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_9': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val() + 9); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_clear': function() { this.$('#o_hr_attendance_PINbox').val(''); this.internal_set_value(this.$('#o_hr_attendance_PINbox').val())},
        'click .o_hr_attendance_pin_pad_button_bksp': function() { this.$('#o_hr_attendance_PINbox').val(this.$('#o_hr_attendance_PINbox').val().slice(0, -1)); },
    },
    init: function() {
        this._super.apply(this, arguments);
        this.set("value", "");
    },
    start: function() {
        this.display_field();
        return this._super();

    },
    display_field: function() {
        this.$el.html(QWeb.render("PinPad"));
    },
});

core.form_widget_registry.add('hr_attendance_pin_pad', PinPad);

});