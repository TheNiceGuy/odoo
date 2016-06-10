odoo.define('hr_attendance.main_menu', function (require) {
"use strict";

var core = require('web.core');
var data = require('web.data');
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
        // "click .button_visitors": function(){ do visitor stuff },
    },

    init: function (parent, action) {
        // Note: BarcodeHandlerMixin.init calls this._super.init, so there's no need to do it here.
        // Yet, "_super" must be present in a function for the class mechanism to replace it with the actual parent method.
        this._super;
        BarcodeHandlerMixin.init.apply(this, arguments);
        var self = this;
    },

    start: function () {
        var self = this;
        self.hide_navbar_if_required();

        var hr_employee = new Model('hr.employee');
        hr_employee.query(['company_id'])
            .filter([['user_id', '=', self.session.uid]])
            .all()
            .then(function (employees) {
                var res_company = new Model('res.company');
                res_company.query(['name', 'logo'])
                   .filter([['id', '=', employees[0].company_id[0]]])
                   .all()
                   .then(function (companies){
                        self.$('.o_hr_attendance_my_company').append(companies[0].name);
                        self.$('.o_hr_attendance_company_logo').append('<img src="data:image/png;base64,' + companies[0].logo + '" alt="Company Logo"/>');
                    });
            });

        self.start_clock();
        self._super();
    },

    hide_navbar_if_required: function (force) {
        if(force){
            $(document).find('.o_main_navbar').fadeOut();
            return;
        }
        // hide the navbar if the user has no other menu access in hr_attendance
        self = this;
        self.hide_navbar = true;
        
        var ir_module_category = new Model('ir.module.category');
        ir_module_category.query(['id'])
            .filter([['name', '=', 'Human Resources']])
            .all()
            .then(function (module_categories) {
                var res_groups = new Model('res.groups');
                res_groups.query(['users'])
                    .filter([
                        ['name', 'in', ['Manual Attendances', 'Manager', 'Officer', 'Attendances']],
                        ['category_id.id', '=', module_categories[0].id]
                    ]).all()
                    .then( function (groups) {
                        groups.forEach( function (group) {
                            if (self.session.uid in group.users) {
                                self.hide_navbar = false;
                                // console.log("shouldn't hide");
                            }
                        });
                        if(self.hide_navbar){
                            $(document).find('.o_main_navbar').fadeOut();
                        }
                    });
            });
    },

    show_navbar: function () {
        $(document).find('.o_main_navbar').fadeIn();
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
