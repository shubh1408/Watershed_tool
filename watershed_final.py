import arcpy
import os  
from arcpy.sa import *
import arcpy.mapping

in_Dem=arcpy.GetParameterAsText(0)
out_Workspace=arcpy.GetParameterAsText(1)

# Set the output folder as the workspace location
arcpy.env.workspace = os.path.join(out_Workspace)
 
arcpy.env.overwriteOutput = True

mxd = arcpy.mapping.MapDocument("CURRENT")
df = arcpy.mapping.ListDataFrames(mxd)[0]

#Clip Raster Function
def clip_raster(in_raster, rectangle, out_raster,in_template_dataset, nodata_value="#", clipping_geometry="ClippingGeometry", maintain_clipping_extent="MAINTAIN_EXTENT"):
    clip_r=arcpy.Clip_management(in_raster, rectangle, out_raster, in_template_dataset, nodata_value, clipping_geometry, maintain_clipping_extent)    # Clip the raster
    return clip_r

#Clip Feature Layer Function
def clip_featurelayer(in_feature_layer, clip_features, out_feature_layer):
    clip_fl = arcpy.Clip_analysis(in_feature_layer, clip_features, out_feature_layer)    # Clip the feature layer
    return clip_fl

# Raster to Polygon Function
def RasterToPolygon(inRaster, out_Fc):
    out_polygon = arcpy.conversion.RasterToPolygon(inRaster, out_Fc)
    return out_polygon

# Raster to polyline function
def RasterToPolyline(inRaster, out_FC, bg_value):
    out_Polyline = arcpy.conversion.RasterToPolyline(inRaster,out_FC,bg_value)
    return out_Polyline

#project raster function
def project_raster(in_raster, out_raster, out_coordinate_system, resampling_type="NEAREST"):
    arcpy.ProjectRaster_management(in_raster, out_raster, out_coordinate_system, resampling_type=resampling_type)
    return out_raster

# Use the project_raster function
arcpy.AddMessage("DEM Projection started")
out_coordinate_system = arcpy.SpatialReference(3857)  # WGS 1984 Web Mercator
proj_raster=project_raster(in_Dem,out_Workspace + "_Projected_DEM.tif", out_coordinate_system)
arcpy.AddMessage("DEM Projection completed")

# Fill Raster
arcpy.AddMessage("Fill Raster started")
# zLimit = 500
# fill_raster = Fill(proj_raster,zLimit)
fill_raster = Fill(proj_raster)
fill_raster.save(out_Workspace + "_Fill.tif")
arcpy.AddMessage("Fill Raster completed")


# Calculate Flow Direction Raster
arcpy.AddMessage("Flow Direction process started")
flow_dirn = FlowDirection(fill_raster, "NORMAL")
flow_dirn.save(out_Workspace + "_Flow_Direction.tif")
arcpy.AddMessage("Flow Direction process completed")

# Calculate Flow Accumulation Raster
arcpy.AddMessage("Flow Accumulation process started")
flow_acc = FlowAccumulation(flow_dirn, "", "FLOAT","D8")
flow_acc.save(out_Workspace + "_Flow_Accumulation.tif")
arcpy.AddMessage("Flow Accumulation process completed")

#give threshold value for flow accumulation % of maximum flow accumulation value
# Calculate the maximum flow accumulation value
arcpy.AddMessage("Calculating Maximum Flow Accumulation Value")
max_flow_acc = arcpy.GetRasterProperties_management(flow_acc, "MAXIMUM")
max_flow_acc_value = float(max_flow_acc.getOutput(0))

# Set threshold as 5% of the maximum flow accumulation value
threshold = 0.02 * max_flow_acc_value

arcpy.AddMessage("Maximum Flow Accumulation Value: {} ".format(max_flow_acc_value))
arcpy.AddMessage("Threshold for Flow Accumulation: {}".format(threshold))
  
# Raster Calculator
arcpy.AddMessage("Calculating Streams Raster Value")
streams_raster = Con(flow_acc > threshold, 1,0)   # 1 for streams and 0 for non-streams
# streams_raster.save(out_Workspace + "_streams_condn.tif")

# Stream to Feature
arcpy.AddMessage("Converting Streams to Feature")
streams_con_fl = StreamToFeature(streams_raster, flow_dirn, out_Workspace + "_Streams_condn.shp", "SIMPLIFY")

# stream order
arcpy.AddMessage("Calculating Stream Order")
stream_order = StreamOrder(streams_raster, flow_dirn, "STRAHLER")
# stream_order.save(out_Workspace + "_stream_order.tif")
stream_order_fl = StreamToFeature(stream_order, flow_dirn, out_Workspace + "_Stream_Order.shp", "SIMPLIFY")

# Create a basin from the flow direction raster
arcpy.AddMessage("Creating Basin")
basin = Basin(flow_dirn) 
basin.save(out_Workspace + "_Basin.tif")

# Raster to polygon conversion
arcpy.AddMessage("Converting Basin To Polygon")
basin_poly = RasterToPolygon(basin, out_Workspace + "_Basin_poly.shp")  # Convert the raster to polygon

#Process Calculate Areas...
# Add a new field to store area values
arcpy.AddMessage("Calculating Largest Basin Area")
if "Area_sqkm" not in [field.name for field in arcpy.ListFields(basin_poly)]:
    arcpy.AddField_management(basin_poly, "Area_sqkm", "FLOAT",10,5)

#Calculate Area...
arcpy.CalculateField_management(basin_poly, "Area_sqkm", "!shape.area@SQUAREMETERS!", "PYTHON")

#--------------Steps select the largest area polygon and crop basin to that polygon----------------#
# Get the largest area polygon
with arcpy.da.SearchCursor(basin_poly, ["OID@", "Area_sqkm", "SHAPE@"]) as cursor:
    largest_area = 0
    largest_polygon = None
    for row in cursor:
        if row[1] > largest_area:
            largest_area = row[1]
            largest_polygon = row[2]

arcpy.AddMessage("Largest Area Polygon: {} sqkm".format(largest_area))
# -----------------------------------------------------------------------------------------------------#
# Save the largest polygon to the output location
arcpy.CopyFeatures_management([largest_polygon], out_Workspace + "_Largest_Basin.shp")

# Clip the DEM with the largest polygon
arcpy.AddMessage("Clipping Largest Area Basin")
clip_raster(in_Dem, "#", out_Workspace+"_Largest_Basin_Clipped.tif", largest_polygon)

# Set the symbology for the _largest_Basin_Clipped.tif layer 
arcpy.AddMessage("Giving Symbology to the final raster")
clipped_raster = out_Workspace + "_Largest_Basin_Clipped.tif" 
# Path to the reference symbology layer file
symbology_layer_raster = r"C:\\Users\\INSB08203\\OneDrive - WSP O365\\Desktop\\Watershed_Output\\Basin_Color_Ref_tif.lyr" 

# Add the raster layer to the map
raster_layer = arcpy.mapping.Layer(clipped_raster)
arcpy.ApplySymbologyFromLayer_management(raster_layer, symbology_layer_raster)

# Add the layer to the map
arcpy.mapping.AddLayer(df, raster_layer, "TOP")

#Set layer extent
df.extent = raster_layer.getExtent(True)

#clip streams_highest_order_fl with largest basin polygon
clip_featurelayer(stream_order_fl, largest_polygon, out_Workspace + "_Final_Stream.shp")

# Set the symbology for the _clipped_stream_order_fl.shp layer
arcpy.AddMessage("Giving Symbology to the final Stream Feature Layer")
final_feature_layer = out_Workspace + "_Final_Stream.shp"
symbology_Layer_fl = r"C:\\Users\\INSB08203\\OneDrive - WSP O365\\Desktop\\Watershed_Output\\Stream_order_fl_Ref.lyr"

feature_layer= arcpy.mapping.Layer(final_feature_layer)
arcpy.ApplySymbologyFromLayer_management(feature_layer, symbology_Layer_fl)

# Add the layer to the map
arcpy.mapping.AddLayer(df, feature_layer, "TOP")

# Refresh the map view after the process is complete
arcpy.RefreshActiveView()
arcpy.RefreshTOC()

arcpy.AddMessage("Process completed successfully and map view refreshed.")
