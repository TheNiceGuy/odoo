odoo.define('hr_attendance.main_menu', function (require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');
var Session = require('web.session');
var BarcodeHandlerMixin = require('barcodes.BarcodeHandlerMixin');


var _t = core._t;

var MainMenu = Widget.extend(BarcodeHandlerMixin, {
    template: 'HrAttendanceMainMenu',

    events: {
        "click .button_employees": function(){ this.do_action('hr_attendance.hr_employee_attendance_action_kanban'); },
        "click .button_inventory": function(){ this.open_inventory(); },
    },

    init: function(parent, action) {
        // Note: BarcodeHandlerMixin.init calls this._super.init, so there's no need to do it here.
        // Yet, "_super" must be present in a function for the class mechanism to replace it with the actual parent method.
        this._super;
        BarcodeHandlerMixin.init.apply(this, arguments);
        var self = this;
    },

    start: function() {
        var self = this;
        var model = new Model("hr.employee");
        model.call("get_company_name").then(function(result) {
            self.$('.o_hr_attendance_my_company').append(result['company_name']);
            self.$('.o_hr_attendance_company_logo').append('<img src="data:image/png;base64,' + result['company_logo'] + '" alt="Company Logo"/>');

        });
        self.start_clock();
    },

    start_clock: function() {
        var self = this;
        this.timer_start = setInterval(function() {self.refresh_clock();},500);
        // First timer refresh before interval to avoid delay
        self.refresh_clock();
    },

    refresh_clock: function() {
        var now = new Date();
        var h = now.getHours();
        var m = now.getMinutes();
        var s = now.getSeconds();
        m = (m > 9 ? m : "0"+m);
        s = (s > 9 ? s : "0"+s); 
        this.$(".o_hr_attendance_clock").text(h + ":" + m + ":" + s);
    },

    on_barcode_scanned: function(barcode) {
        var self = this;
        Session.rpc('/hr_attendance/scan_from_main_menu', {
            barcode: barcode,
        }).then(function(result) {
            if (result.action) {
                self.do_action(result.action);
            } else if (result.warning) {
                self.do_warn(result.warning);
            }
        });
    },
});

core.action_registry.add('hr_attendance_main_menu', MainMenu);

return {
    MainMenu: MainMenu,
};

});
