odoo.define('hr_attendance.farewell_message', function (require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');
var Session = require('web.session');


var _t = core._t;

var FarewellMessage = Widget.extend({
    template: 'HrAttendanceMessage',

    events: {
        "click .button_dismiss": function(){ 
            clearTimeout(this.return_to_main_menu);
            this.do_action(this.next_action, {clear_breadcrumbs: true}); 
        },
    },

    init: function(parent, action) {
        this._super.apply(this, arguments);
        this.res_id = action.res_id;
        this.next_action = action.next_action || 'hr_attendance.hr_attendance_action_main_menu';
    },

    start: function() {
        var self = this;
        var model = new Model("hr.employee");
        var now = new Date();
        var current_time = now.toTimeString().slice(0,8);
        model.query(['name', 'last_check']).filter([['id', '=', this.res_id]]).all().then(function(employees) {
            if(employees[0]){
                self.$('.o_hr_attendance_validation').append(_t("Check out validated"));
                self.$('.o_hr_attendance_message_time').append(current_time);
                if(employees[0].last_check){
                    var last_check_date = new Date(employees[0].last_check);  // or should the traduction hold employee name as well?
                    if(last_check_date.getDate() != now.getDate()){
                        self.$('.o_hr_attendance_warning_message').append(_t("<h2>Warning! Last check in wasn't today.<br/>If this isn't right, please contact Human Resources.</h2>"));
                    } else if(now.valueOf() - last_check_date.valueOf() > 1000*60*60*12){
                        self.$('.o_hr_attendance_warning_message').append(_t("<h2>Warning! Last check in was over 12 hours ago.<br/>If this isn't right, please contact Human Resources.</h2>"));
                    } else if(now.valueOf() - last_check_date.valueOf() > 1000*60*60*8){
                        self.$('.o_hr_attendance_random_message').append(_t("<h3>Another good day's work! See you soon!</h3>"));
                    // } else {
                    //     self.$('.o_hr_attendance_random_message').append("add random quote ? (based on various conditions or do not do unnecessary computations?)");
                    }
                }

                self.$('.o_hr_attendance_message_message').append(_t("Goodbye ") + employees[0].name + ".");
                if(now.getHours()<12){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Have a good day!"));
                } else if(now.getHours()<14){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Have a nice lunch!"));
                } else if(now.getHours()<17){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Have a good afternoon."));
                } else if(now.getHours()){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Have a good evening."));
                } 
            } else {
                self.$('.o_hr_attendance_message_time').append(_t("Invalid request, please return to the main menu."));
            }
        });
        this.return_to_main_menu = setTimeout( function() { self.do_action(self.next_action, {clear_breadcrumbs: true}); }, 5000);
    },
});

core.action_registry.add('hr_attendance_farewell_message', FarewellMessage);

});
