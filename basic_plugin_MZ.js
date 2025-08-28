/*:
 * @target MZ
 * @plugindesc A simple sample plugin for RPG Maker MV.
 * @author Paradise Union
 *
 * @param MessageText
 * @type text
 * @default Hello, RPG Maker MV!
 * @desc The text to display in the console.
 *
 * @help
 * This script is a basic plugin establishing structure and parameter usage.
 * The plugin logs a message to the console when the game starts.
 * Any message will be shown from plugin parameters.
 */

(function() {
    // Get plugin parameters
    var parameters = PluginManager.parameters('SamplePluginName'); // Replace 'SamplePluginName' with the actual filename without .js
    var messageText = String(parameters['MessageText'] || 'Hello, RPG Maker MV!');

    // Alias the Scene_Boot.prototype.start function to add custom code
    var _Scene_Boot_start = Scene_Boot.prototype.start;
    Scene_Boot.prototype.start = function() {
        _Scene_Boot_start.call(this); // Call the original Scene_Boot.prototype.start function
        console.log(messageText); // Log the message to the console
    };
})();