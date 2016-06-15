odoo.define('hr_attendance.basic_employee_main_menu', function (require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var formats = require('web.formats');
var Widget = require('web.Widget');
var time = require('web.time');
var Session = require('web.session');

var _t = core._t;


var BasicEmployeeMainMenu = Widget.extend({
    template: 'HrAttendanceBasicEmployeeMainMenu',

    events: {
        "click .button_employees": function(){ this.do_action('hr_attendance.hr_employee_attendance_action_kanban'); },
        // "click .button_visitors": function(){ do visitor stuff },
    },

    init: function (parent) {
        this._super(parent);
        this.set({"signed_in": false});
        self.employee = false;
        self.last_check = false;
    },

    start: function () {
        var self = this;

        this.check_attendance();
        self.$('.o_hr_attendance_check_message').append((this.signed_in ? _t("Click the button below to check out") :_t("Click the button below to check in")));
        
        var tmp = function() {
            var $sign_in_out_icon = self.$('#oe_attendance_sign_in_out_icon');
            $sign_in_out_icon.toggleClass("fa-sign-in", ! self.get("signed_in"));
            $sign_in_out_icon.toggleClass("fa-sign-out", self.get("signed_in"));
        };
        this.on("change:signed_in", this, tmp);
        _.bind(tmp, this)();
        this.$(".oe_attendance_sign_in_out").click(function(ev) {
            ev.preventDefault();
            self.do_update_attendance();
        });

        var hr_employee = new Model('hr.employee');
        hr_employee.query(['company_id', 'name'])
            .filter([['user_id', '=', self.session.uid]])
            .all()
            .then(function (employees) {
                self.$('.o_hr_attendance_employee').append(employees[0].name);
                // var res_company = new Model('res.company');
                // res_company.query(['name', 'logo'])
                //    .filter([['id', '=', employees[0].company_id[0]]])
                //    .all()
                //    .then(function (companies){
                //         self.$('.o_hr_attendance_company_logo').append('<img src="data:image/png;base64,' + companies[0].logo + '" alt="Company Logo"/>');
                //     });
            });

        return self.start_clock();
    },

    do_update_attendance: function () {
        var self = this;
        var hr_employee = new Model('hr.employee');
        debugger;
        Session.rpc('/hr_attendance/basic_change_attendance', {
            'employee_id': self.employee.id, 
        }).then(function(result) {
            if (result.action) {
                self.last_check = new Date();
                self.set({"signed_in": ! self.get("signed_in")});
                self.do_action(result.action);
            } else if (result.warning) {
                self.do_warn(result.warning);
            }
        });
    },

    check_attendance: function () {
        var self = this;
        var hr_employee = new Model('hr.employee');
        hr_employee.query(['state', 'last_check'])
            .filter([['user_id', '=', self.session.uid]])
            .all()
            .then(function (res) {
            if (_.isEmpty(res) )
                return;
            self.employee = res[0];
            self.last_check = time.str_to_datetime(self.employee.last_check);
            self.set({"signed_in": self.employee.state !== "absent"});
        });
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
});

core.action_registry.add('hr_attendance_basic_employee_main_menu', BasicEmployeeMainMenu);

});
