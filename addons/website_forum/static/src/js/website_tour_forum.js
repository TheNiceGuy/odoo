odoo.define("website_forum.tour_forum", function (require) {
    "use strict";

    var core = require("web.core");
    var tour = require("web_tour.tour");
    var base = require("web_editor.base");

    var _t = core._t;

    base.ready().done(function () {
        tour.register("question", {
            skip_enabled: true,
            url: "/forum",
        }, [{
            trigger: "#oe_main_menu_navbar a[data-action=new_page]",
            content: _t("Use this button to create a new forum like any other document (page, menu, products, event, ...)."),
            position: "bottom",
        }, {
            trigger: "a[data-action=new_forum]",
            content: _t("Select this menu item to create a new forum."),
            position: "left",
        }, {
            trigger: "#editor_new_forum input[type=text]",
            content: _t("Enter a name for your new forum."),
            position: "right",
        }, {
            trigger: "button.btn-primary",
            extra_trigger: ".modal #editor_new_forum input[type=text]:not(:propValue(\"\"))",
            content: _t("Click <em>Continue</em> to create the forum."),
            position: "right",
        }, {
            trigger: "#wrap",
            extra_trigger: "body:not(.modal-open)",
            content: _t("This page contains all the information related to the new forum."),
            position: "top",
        }, {
            trigger: ".btn-block a:first",
            position: "left",
            content: _t("Ask the question in this forum by clicking on the button."),
        }, {
            trigger: "input[name=post_name]",
            position: "top",
            content: _t("Give your question title."),
        }, {
            trigger: ".note-editable p",
            extra_trigger: "input[name=post_name]:not(:propValue(\"\"))",
            content: _t("Put your question here."),
            position: "top",
        }, {
            trigger: ".select2-choices",
            extra_trigger: ".note-editable p:not(:containsExact(\"<br>\"))",
            content: _t("Insert tags related to your question."),
            position: "top",
        }, {
            trigger: "button:contains(\"Post Your Question\")",
            extra_trigger: "input[id=s2id_autogen2]:not(:propValue(\"Tags\"))",
            content: _t("Click to post your question."),
            position: "bottom",
        }, {
            trigger: "#wrap",
            extra_trigger: ".fa-star",
            content: _t("This page contains the newly created questions."),
            position: "top",
        }, {
            trigger: ".note-editable p",
            content: _t("Put your answer here."),
            position: "top",
        }, {
            trigger: "button:contains(\"Post Answer\")",
            extra_trigger: ".note-editable p:not(:containsExact(\"<br>\"))",
            content: _t("Click to post your answer."),
            position: "bottom",
        }, {
            trigger: "#wrap",
            extra_trigger: ".fa-check-circle",
            content: _t("This page contains the newly created questions and its answers."),
            position: "top",
        }, {
            trigger: "a[data-karma=\"20\"]:first",
            content: _t("Click here to accept this answer."),
            position: "right",
        }, {
            trigger: "#wrap",
            extra_trigger: ".oe_answer_true",
            content: _t("Congratulations! You just created and post your first question and answer."),
            position: "top",
        }]);
    });
});
