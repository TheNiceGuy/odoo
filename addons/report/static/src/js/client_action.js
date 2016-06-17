odoo.define('report.client_action', function (require) {
'use strict';

var core = require('web.core');
var ControlPanelMixin = require('web.ControlPanelMixin');
var Widget = require('web.Widget');
var Model = require('web.Model');

var QWeb = core.qweb;

var ReportAction = Widget.extend(ControlPanelMixin, {
    tagName: 'iframe',

    init: function (parent, action, options) {
        this._super.apply(this, arguments);
        this.action = action;
        this.options = options || {};
        this.action_manager = parent;

        core.bus.on('message', this, this.on_message_received);
    },

    start: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self.$buttons = $(QWeb.render("report.client_action.ControlButtons", {}));
            self.$buttons.on('click', '.o_report_edit', self.on_click_edit);
            self.$buttons.on('click', '.o_report_print', self.on_click_print);

            self.$el.css({
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                left: 0,
                width: "100%",
                height: "100%",
                border: "none",
            });

            self.el.src = self.action.report_url;

            self.update_control_panel({
                breadcrumbs: self.action_manager.get_breadcrumbs(),
                cp_content: {
                    $buttons: self.$buttons,
                },
            });
        })
    },

    on_message_received: function (ev) {
        if (ev.originalEvent.source.location.host === window.location.host &&
                ev.originalEvent.source.location.protocol === window.location.protocol) {
            switch(ev.originalEvent.data) {
                case 'do_action':
                    this.do_action(ev.originalEvent.data);
                    break;
                default:
                    console.log('nothing to do for ' + ev.originalEvent.data);
            }
        }
    },

    on_click_edit: function () {
        this.el.src = this.action.report_url + '?enable_editor=1';
    },

    on_click_discard: function () {
        this.el.src = this.action.report_url;
    },

    on_click_save: function () {
        this.el.postMessage('web_editor_save');
    },

    on_click_print: function () {
        console.log('fixmefixmefixme');
    },
});

core.action_registry.add('report.client_action', ReportAction);

});
