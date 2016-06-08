odoo.define('hr_attendance.welcome_message', function (require) {
"use strict";

var core = require('web.core');
var Model = require('web.Model');
var Widget = require('web.Widget');
var Dialog = require('web.Dialog');
var Session = require('web.session');


var _t = core._t;

var WelcomeMessage = Widget.extend({
    template: 'HrAttendanceMessage',

    events: {
        "click .button_dismiss": function(){ 
            clearTimeout(this.return_to_main_menu);
            this.do_action('hr_attendance.hr_attendance_action_main_menu', {clear_breadcrumbs: true}); 
        },
    },

    init: function(parent, action) {
        this._super.apply(this, arguments);
        this.res_id = action.res_id;
    },

    start: function() {
        var self = this;
        var model = new Model("hr.employee");
        var now = new Date();
        var current_time = now.toTimeString().slice(0,9);
        model.query(['name', 'last_check']).filter([['id', '=', this.res_id]]).all().then(function(employees) {
            if(employees[0]){
                self.$('.o_hr_attendance_validation').append(_t("Check in validated"));
                self.$('.o_hr_attendance_message_time').append(current_time);
                self.$('.o_hr_attendance_message_message').append(_t("Welcome ") + employees[0].name + "!");
                if(now.getHours()<8){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>The early bird catches the worm."));
                } else if(now.getHours()<12){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Good morning."));
                } else if(now.getHours()<17){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Good afternoon."));
                } else if(now.getHours()){
                    self.$('.o_hr_attendance_message_message').append(_t("<br/>Good evening."));
                } 
                if(employees[0].last_check){
                    var last_check_date = new Date(employees[0].last_check);
                    if(now.valueOf() - last_check_date.valueOf() > 1000*60*60*24*7){
                        self.$('.o_hr_attendance_random_message').append(_t("<h3>Glad to have you back, it's been a while!</h3>"));
                    // } else {
                    //     self.$('.o_hr_attendance_random_message').append("add random quote ? (based on various conditions or do not do unnecessary computations?)");
                    }
                }
                // add random easter egg messages ? (first ones arrived / X days in a row / weekend / back from holiday (/sick leave ? ) or just "it's been a while !" / ...
            } else {
                self.$('.o_hr_attendance_message_time').append(_t("Invalid request, please return to the main menu."));
            }
        });
        this.return_to_main_menu = setTimeout(function(){ self.do_action('hr_attendance.hr_attendance_action_main_menu', {clear_breadcrumbs: true}); }, 5000);
    },
});

core.action_registry.add('hr_attendance_welcome_message', WelcomeMessage);

});
