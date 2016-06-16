odoo.define("website.tour.banner", function (require) {
    "use strict";

    var core = require("web.core");
    var tour = require("web_tour.tour");
    var base = require("web_editor.base");

    var _t = core._t;

    base.ready().done(function () {
        tour.register("banner", {
            skip_enabled: true,
            url: "/page/homepage",
        }, [{
            trigger: "a[data-action=edit]",
            content: _t("Every page of your website can be modified through the <b>Edit</b> button."),
            position: "bottom",
        }, {
            trigger: "#snippet_structure .oe_snippet:eq(1)",
            content: _t("Drag the Cover block and drop it in your page."),
            position: "bottom",
        }, {
            trigger: "#wrapwrap .s_text_block_image_fw h2",
            extra_trigger: ".oe_overlay_options .oe_options",
            content: _t("Click in the title text and start editing it."),
            position: "left",
        }, {
            trigger: ".oe_snippet_parent",
            extra_trigger: "#wrapwrap .s_text_block_image_fw h2:not(:containsExact(\"Headline\"))",
            content: _t("Select the parent container to get the global options of the banner."),
            position: "left",
        }, {
            trigger: ".oe_overlay_options .oe_options",
            content: _t("Customize any block through this menu. Try to change the background of the banner."),
            position: "right",
        }, {
            trigger: "#snippet_structure .oe_snippet:eq(6)",
            content: _t("Drag the \"Features\" block and drop it below the banner."),
            position: "bottom",
        }, {
            trigger: "button[data-action=save]",
            extra_trigger: ".oe_overlay_options .oe_options",
            content: _t("Publish your page by clicking on the <b>Save</b> button."),
            position: "bottom",
        }, {
            trigger: "a[data-action=show-mobile-preview]",
            content: _t("Well done, you created your homepage.<br/>Let's check how your homepage looks like on mobile devices."),
            position: "bottom",
        }, {
            trigger: ".modal-dialog:has(#mobile-viewport) button[data-dismiss=modal]",
            content: _t("Scroll to check rendering and then close the mobile preview."),
            position: "right",
        }, {
            trigger: "#content-menu-button",
            extra_trigger: "body:not(.modal-open)",
            content: _t("The <b>Content</b> menu allows you to rename and delete pages or add them to the top menu."),
            position: "bottom",
        }, {
            trigger: "#oe_main_menu_navbar a[data-action=new_page]",
            content: _t("Use this button to add pages"),
            position: "bottom",
        }]);
    });
});
