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

        this.in_edit_mode = false;

        core.bus.on('message', this, this.on_message_received);
    },

    start: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self.$buttons = $(QWeb.render('report.client_action.ControlButtons', {}));
            self.$buttons.on('click', '.o_report_edit', self.on_click_edit);
            self.$buttons.on('click', '.o_report_print', self.on_click_print);
            self.$buttons.on('click', '.o_report_save', self.on_click_save);
            self.$buttons.on('click', '.o_report_discard', self.on_click_discard);

            self.$el.css({
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                left: 0,
                width: '100%',
                height: '100%',
                border: 'none',
            });

            self.el.src = self.action.report_url;

            self.update_control_panel({
                breadcrumbs: self.action_manager.get_breadcrumbs(),
                cp_content: {
                    $buttons: self.$buttons,
                },
            });
            self._update_control_panel_buttons();
        });
    },

    _update_control_panel_buttons: function () {
        this.$buttons.filter('div.o_report_edit_mode').toggle(this.in_edit_mode);
        this.$buttons.filter('div.o_report_no_edit_mode').toggle(! this.in_edit_mode);
    },

    on_message_received: function (ev) {
        if (ev.originalEvent.source.location.host === window.location.host &&
                ev.originalEvent.source.location.protocol === window.location.protocol) {
            switch(ev.originalEvent.data) {
                case 'report.editor:save_ok':
                    this.el.src = this.action.report_url;  // reload to disable the editor
                    this.in_edit_mode = false;
                    this._update_control_panel_buttons();
                    break;
                case 'report.editor:discard_ok':
                    this.el.src = this.action.report_url; // reload to disable the editor
                    this.in_edit_mode = false;
                    this._update_control_panel_buttons();
                    break;
                default:
                    console.log('nothing to do for ' + ev.originalEvent.data);
            }
        }
    },

    on_click_edit: function () {
        this.el.src = this.action.report_url + '?enable_editor=1';
        this.in_edit_mode = true;
        this._update_control_panel_buttons();
    },

    on_click_discard: function () {
        this.el.contentWindow.postMessage('report.editor:ask_discard', 'http://127.0.0.1:8069');
    },

    on_click_save: function () {
        this.el.contentWindow.postMessage('report.editor:ask_save', 'http://127.0.0.1:8069');
    },

    on_click_print: function () {
        console.log('fixmefixmefixme');
    },
});

core.action_registry.add('report.client_action', ReportAction);

});
