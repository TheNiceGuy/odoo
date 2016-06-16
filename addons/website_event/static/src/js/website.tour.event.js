odoo.define("website_event.tour", function (require) {
    "use strict";

    var core = require("web.core");
    var tour = require("web_tour.tour");
    var base = require("web_editor.base");

    var _t = core._t;

    base.ready().done(function () {
        tour.register("event", {
            skip_enabled: true,
            url: "/event",
        }, [{
            trigger: "#oe_main_menu_navbar a[data-action=new_page]",
            content: _t("This button allows you to create new pages, events, menus, etc."),
            position: "bottom",
        }, {
            trigger: "a[data-action=new_event]",
            content: _t("Click here to create a new event."),
            position: "left",
        }, {
            trigger: ".modal-dialog #editor_new_event input[type=text]",
            content: _t("Create a name for your new event and click <em>\"Continue\"</em>. e.g: Technical Training"),
            position: "right",
        }, {
            trigger: ".modal-dialog button.btn-primary.btn-continue",
            extra_trigger: ".modal-dialog #editor_new_event input[type=text][value!=\"\"]",
            content: _t("Click <em>Continue</em> to create the event."),
            position: "right",
        }, {
            trigger: "#wrap",
            extra_trigger: "#o_scroll .oe_snippet",
            content: _t("This is your new event page. We will edit the event presentation page."),
            position: "top",
        }, {
            trigger: "#snippet_structure .oe_snippet:eq(2)",
            content: _t("Drag this block and drop it in your page."),
            position: "bottom",
        }, {
            trigger: "button[data-action=save]",
            content: _t("Once you click on save, your event is updated."),
            position: "bottom",
        }, {
            trigger: "button.btn-danger.js_publish_btn",
            extra_trigger: "body:not(.editor_enable)",
            content: _t("Click to publish your event."),
            position: "top",
        }, {
            trigger: ".js_publish_management button[data-toggle=\"dropdown\"]",
            extra_trigger: ".js_publish_management button.js_publish_btn.btn-success:visible",
            content: _t("Click here to customize your event further."),
            position: "left",
        }]);
    });
});
