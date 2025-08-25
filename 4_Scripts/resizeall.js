// DESCRIPTION: Batch-processes InDesign files for Project Indigo.
// Merged version: Retains original InDesign HTML export and adds a supplementary asset gallery (index.html).

// --- CONFIGURATION ---
var SCALE_FACTOR = 8;
// UPDATED output path as per new requirement.
var OUTPUT_ROOT_PATH = "C:/Users/Admin/Documents/nctv-repositories/html-flyers-static/flyers";
var exportedImages = []; // Global array to store info for the HTML gallery.

// --- MAIN FUNCTION ---
function runSequentialBatchExport() {
    var sourceFolder = Folder.selectDialog("Select the folder containing your InDesign files");
    if (sourceFolder === null) return;

    var outputRootFolder = new Folder(OUTPUT_ROOT_PATH);
    if (!outputRootFolder.exists) outputRootFolder.create();

    var inddFiles = sourceFolder.getFiles("*.indd");
    if (inddFiles.length === 0) {
        alert("INDIGO_RESIZE_COMPLETE");
        return;
    }

    for (var i = 0; i < inddFiles.length; i++) {
        var inddFile = inddFiles[i];
        var doc = null;
        try {
            doc = app.open(inddFile, false);
            var docName = doc.name.replace(/\.indd$/i, "");

            var mainExportFolder = new Folder(outputRootFolder.fsName + "/" + docName);
            if (!mainExportFolder.exists) mainExportFolder.create();

            var imageSubfolder = new Folder(mainExportFolder.fsName + "/publication-web-resources/image");
            if (!imageSubfolder.exists) imageSubfolder.create();

            exportHighResAssets(doc, imageSubfolder, docName);

        } catch (e) {
            // Instead of failing silently, we now display a loud, blocking alert
            // with the actual error message from InDesign. This will stop the
            // script and prevent a false success signal.
            alert("FATAL SCRIPT ERROR processing '" + inddFile.name + "':\n\n" + e.message);
            
            // We must explicitly stop the function here.
            if (doc !== null) { doc.close(SaveOptions.NO); }
            return; 

        } finally {
            if (doc !== null && doc.isValid) {
                doc.close(SaveOptions.NO);
            }
        }
    }
    
    generateHTMLIndex();

    // This alert will now ONLY be reached if every single file succeeds.
    alert("INDIGO_RESIZE_COMPLETE");
}


// --- PNG EXPORT HELPER (Your proven code, enhanced to collect data) ---
function exportHighResAssets(doc, destinationFolder, docName) {
    // Clear old assets to ensure a clean export
    var oldFiles = destinationFolder.getFiles();
    for (var f = 0; f < oldFiles.length; f++) {
        try { oldFiles[f].remove(); } catch (e) {}
    }

    app.pngExportPreferences.exportResolution = 72 * SCALE_FACTOR;
    app.pngExportPreferences.pngQuality = PNGQualityEnum.MAXIMUM;
    app.pngExportPreferences.transparentBackground = true;

    var allGraphics = doc.allGraphics;
    if (allGraphics.length === 0) return;

    for (var i = 0; i < allGraphics.length; i++) {
        var graphic = allGraphics[i];
        var itemToExport = graphic.parent;
        var baseName = "";

        if (graphic.itemLink && graphic.itemLink.isValid && graphic.itemLink.name) {
            baseName = graphic.itemLink.name.replace(/\.[^\.]+$/, "");
        } else {
            baseName = "embedded_asset_" + (i + 1);
        }

        baseName = baseName.replace(/\s/g, "_").replace(/[:\/\\*\?\"\<\>\|]/g, "_");
        var finalFileName = baseName + ".png";
        var filePath = new File(destinationFolder.fsName + "/" + finalFileName);
        
        try {
            itemToExport.exportFile(ExportFormat.PNG_FORMAT, filePath, false);
            $.writeln("Exported: " + finalFileName);

            // --- ADDITION ---
            // Store image info for the new HTML gallery generation.
            exportedImages.push({
                fileName: finalFileName,
                relativePath: "./" + finalFileName, // Relative path for use in HTML
                docName: docName,
                folder: destinationFolder
            });
            
        } catch (e) {
            $.writeln("Failed to export: " + finalFileName + " — " + e.message);
        }
    }
}

// --- NEW FEATURE: HTML GALLERY GENERATION (From developer's script) ---
function generateHTMLIndex() {
    if (exportedImages.length === 0) {
        $.writeln("No images to generate HTML gallery for.");
        return;
    }
    
    var imagesByDoc = {};
    var imageFolders = {};
    
    for (var i = 0; i < exportedImages.length; i++) {
        var img = exportedImages[i];
        if (!imagesByDoc[img.docName]) {
        imagesByDoc[img.docName] = [];
        imageFolders[img.docName] = img.folder; // Store the target folder for each doc
        }
        imagesByDoc[img.docName].push(img);
    }
    
    for (var docName in imagesByDoc) {
        var images = imagesByDoc[docName];
        var htmlContent = generateHTMLContent(docName, images);
        
        // Save the gallery as "index.html" inside the image subfolder.
        var htmlFile = new File(imageFolders[docName].fsName + "/index.html");
        
        try {
            htmlFile.open("w");
            htmlFile.encoding = "UTF-8";
            htmlFile.write(htmlContent);
            htmlFile.close();
        $.writeln("Generated HTML gallery: " + htmlFile.fsName);
        } catch (e) {
            $.writeln("Failed to generate HTML gallery: " + e.message);
        }
    }
}

// --- NEW FEATURE: HTML CONTENT HELPER (From developer's script) ---
function generateHTMLContent(docName, images) {
    var html = '<!DOCTYPE html>\n';
    html += '<html lang="en">\n';
    html += '<head>\n';
    html += '    <meta charset="UTF-8">\n';
    html += '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n';
    html += '    <title>Exported Images - ' + docName + '</title>\n';
    html += '    <style>\n';
    html += '        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }\n';
    html += '        .container { max-width: 1600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }\n';
    html += '        h1 { color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; margin-bottom: 20px; }\n';
    html += '        .stats { background: #e7f3ff; padding: 15px; border-radius: 5px; margin-bottom: 25px; text-align: center; }\n';
    html += '        .image-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 15px; width: 100%; }\n';
    html += '        .image-item { padding: 10px; border: 1px solid #ddd; border-radius: 5px; background: #fafafa; text-align: center; display: flex; flex-direction: column; }\n';
    html += '        .filename { font-weight: bold; color: #007acc; margin-bottom: 10px; font-size: 12px; word-break: break-word; }\n';
    html += '        .image-container { flex: 1; display: flex; align-items: center; justify-content: center; border: 1px solid #ccc; border-radius: 4px; background: white; overflow: hidden; aspect-ratio: 1; }\n';
    html += '        img { width: 100%; height: 100%; object-fit: contain; }\n';
    html += '        @media (max-width: 1200px) { .image-grid { grid-template-columns: repeat(6, 1fr); } }\n';
    html += '        @media (max-width: 900px) { .image-grid { grid-template-columns: repeat(4, 1fr); } }\n';
    html += '        @media (max-width: 600px) { .image-grid { grid-template-columns: repeat(3, 1fr); } }\n';
    html += '        @media (max-width: 400px) { .image-grid { grid-template-columns: repeat(2, 1fr); } }\n';
    html += '    </style>\n';
    html += '</head>\n';
    html += '<body>\n';
    html += '    <div class="container">\n';
    html += '        <h1>Exported Images from: ' + docName + '</h1>\n';
    html += '        <div class="stats">\n';
    html += '            <strong>Total Images:</strong> ' + images.length + ' | ';
    html += '            <strong>Export Resolution:</strong> ' + (72 * SCALE_FACTOR) + ' DPI | ';
    html += '            <strong>Scale Factor:</strong> ' + SCALE_FACTOR + 'x\n';
    html += '        </div>\n';
    html += '        <div class="image-grid">\n';
    
    for (var i = 0; i < images.length; i++) {
        var img = images[i];
        html += '            <div class="image-item">\n';
        html += '                <p class="filename">' + img.fileName + '</p>\n';
        html += '                <div class="image-container">\n';
        html += '                    <img src="' + img.relativePath + '" alt="' + img.fileName + '">\n';
        html += '                </div>\n';
        html += '            </div>\n';
    }
    
    html += '        </div>\n';
    html += '    </div>\n';
    html += '</body>\n';
    html += '</html>';
    
    return html;
}

// --- EXECUTION BLOCK (Your proven code - UNCHANGED) ---
try {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    runSequentialBatchExport();
} catch (e) {
    $.writeln("Critical error: " + e.message);
} finally {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
}