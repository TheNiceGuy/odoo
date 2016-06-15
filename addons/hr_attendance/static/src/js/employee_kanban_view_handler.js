
odoo.define('hr_attendance.employee_kanban_view_handler', function(require) {
"use strict";

var KanbanRecord = require('web_kanban.Record');
var Model = require('web.Model');

KanbanRecord.include({
    on_card_clicked: function() {
        if (this.model === 'hr.employee' && this.$el.parents('.o_hr_employee_attendance_kanban').length) { 
                                            // needed to diffentiate attendance menu kanban view of employees <-> employee menu kanban view
            var self = this;
            var IrConfigParam = new Model('ir.config_parameter')
            IrConfigParam.call('get_param', ['attendance_use_employee_pin'])
                .then( function (result) {
                    var action = {
                        type: 'ir.actions.act_window',
                        res_model: 'hr_attendance.pin_pad',
                        src_model: 'hr.employee',
                        view_mode: 'form',
                        views: [[false, 'form']],
                        target: 'new',
                        // options: {'dialogClass': 'modal-sm'},
                        // res_id: this.record.id.raw_value,
                        context: {'employee_id': self.record.id.raw_value}, // 'form_view_initial_mode': 'edit', 
                    };
                    self.do_action(action);
                })
        } else {
            this._super.apply(this, arguments);
        }
    }
});

});
