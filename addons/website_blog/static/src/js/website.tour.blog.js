odoo.define("website_blog.tour", function (require) {
    "use strict";

    var core = require("web.core");
    var tour = require("web_tour.tour");
    var base = require("web_editor.base");

    var _t = core._t;

    base.ready().done(function () {
        tour.register("blog", {
            skip_enabled: true,
            url: "/blog",
        }, [{
            trigger: "#oe_main_menu_navbar a[data-action=new_page]",
            content: _t("Use this button to create a new blog post like any other document (page, menu, products, event, ...)."),
            position: "bottom",
        }, {
            trigger: "a[data-action=new_blog_post]",
            content: _t("Select this menu item to create a new blog post."),
            position: "left",
        }, {
            trigger: "#wrap",
            extra_trigger: "#o_scroll .oe_snippet",
            content: _t("This is your new blog post. Let's edit it."),
            position: "top",
        }, {
            trigger: "h1[data-oe-expression=\"blog_post.name\"]",
            content: _t("Write a title, the subtitle is optional."),
            position: "top",
        }, {
            trigger: "#oe_manipulators .oe_overlay.oe_active a.btn.btn-primary.btn-sm",
            extra_trigger: "#wrap h1[data-oe-expression=\"blog_post.name\"]:not(:containsExact(\"\"))",
            content: _t("Change and customize your blog post cover."),
            position: "right",
        }, {
            trigger: "a:containsExact(" + _t("Change Cover")+ "):eq(1)",
            content: _t("Select this menu item to change blog cover."),
            position: "right",
        }, {
            trigger: ".o_select_media_dialog .o_existing_attachment_cell:nth(1) img",
            extra_trigger: ".modal:has(.o_existing_attachment_cell:nth(1))",
            content: _t("Choose an image from the library."),
            position: "top",
        }, {
            trigger: ".o_select_media_dialog .btn.o_save_button",
            extra_trigger: ".o_existing_attachment_cell.o_selected",
            content: _t("Click on <b>Save</b> to set the picture as cover."),
            position: "top",
        }, {
            trigger: ".blog_content section.mt16",
            content: _t("Start writing your story here."),
            position: "top",
        }, {
            trigger: "button[data-action=save]",
            extra_trigger: "#blog_content section:first p:first:not(:containsExact(" + _t("Start writing here...") + "))",
            content: _t("Click on <b>Save</b> button to record changes on the page."),
            position: "bottom",
        }, {
            trigger: "a[data-action=show-mobile-preview]",
            extra_trigger: "body:not(.editor_enable)",
            content: _t("Click on the mobile icon to preview how your blog post will be displayed on a mobile device."),
            position: "bottom",
        }, {
            trigger: "button[data-dismiss=modal]",
            extra_trigger: ".modal:has(#mobile-viewport)",
            content: _t("Scroll to check rendering and then close the mobile preview."),
            position: "right",
        }, {
            trigger: "button.btn-danger.js_publish_btn",
            position: "top",
            content: _t(" Click on this button to send your blog post online."),
        }, {
            trigger: "#wrap h1",
            extra_trigger: ".js_publish_management button.js_publish_btn.btn-success:visible",
            content: _t("This tutorial is over. To discover more features and improve the content of this page, go to the upper left customize menu. You can also add some cool content with your text in the edit mode with the upper right button."),
            position: "top",
            width: 500,
        }]);
    });
});
