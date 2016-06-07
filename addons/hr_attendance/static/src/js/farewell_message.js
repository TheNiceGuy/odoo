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
        var current_time = now.toTimeString().slice(0,8);
        model.query(['name', 'last_check']).filter([['id', '=', this.res_id]]).all().then(function(employees) {
            if(employees[0]){
                self.$('.o_hr_attendance_validation').append(_t("Check out validated"));
                self.$('.o_hr_attendance_message_time').append(current_time);
                if(now.getHours()<10){
                    self.$('.o_hr_attendance_message_message').append(_t("Leaving already? Hope to see you soon again"));
                } else if(now.getHours()<14){
                    self.$('.o_hr_attendance_message_message').append(_t("Have a good lunch ") + employees[0].name);
                } else if(now.getHours()<17){
                    self.$('.o_hr_attendance_message_message').append(_t("Good afternoon ") + employees[0].name);
                } else if(now.getHours()){
                    self.$('.o_hr_attendance_message_message').append(_t("Have a good evening ") + employees[0].name);
                } 
                if(employees[0].last_check){
                    var last_check_date = new Date(employees[0].last_check);
                    if(now.valueOf() - last_check_date.valueOf() > 1000*60*60*8){
                        self.$('.o_hr_attendance_random_message').append(_t("<br/>Another good day of work! See you soon!"));
                    // } else {
                    //     self.$('.o_hr_attendance_random_message').append("add random quote ? (based on various conditions or do not do unnecessary computations?)");
                    }
                }
            } else {
                self.$('.o_hr_attendance_message_time').append(_t("Invalid request, please return to the main menu."));
            }
        });
        this.return_to_main_menu = setTimeout(function(){ self.do_action('hr_attendance.hr_attendance_action_main_menu', {clear_breadcrumbs: true}); }, 5000);
    },
});

core.action_registry.add('hr_attendance_farewell_message', FarewellMessage);

});
