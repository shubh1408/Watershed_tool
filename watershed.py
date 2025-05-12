import arcpy
import os  #######operating system separator##############
import arcpy.management
from arcpy.sa import *


in_Dem=arcpy.GetParameterAsText(0)
out_Workspace=arcpy.GetParameterAsText(1)

# out_Workspace=r"C:\\Users\\INSB08203\\OneDrive - WSP O365\\Arcpy\\Watershed\\Output\\"
# pore_point=arcpy.GetParameterAsText(2)
# in_AOI=arcpy.GetParameterAsText(3)

# Set the output folder as the workspace location
arcpy.env.workspace = out_Workspace
 
arcpy.env.overwriteOutput = True

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
out_coordinate_system = arcpy.SpatialReference(3857)  # WGS 1984 Web Mercator
proj_raster=project_raster(in_Dem,out_Workspace + "_proj.tif", out_coordinate_system)


# Fill(in_surface_raster, {z_limit})
zLimit = 500
fill_raster = Fill(proj_raster,zLimit)
fill_raster.save(out_Workspace + "_fill.tif")

# Calculate Flow Direction Raster
flow_dirn = FlowDirection(fill_raster, "NORMAL")
flow_dirn.save(out_Workspace + "_flow_dirn.tif")


# Calculate Flow Accumulation Raster
flow_acc = FlowAccumulation(flow_dirn, "", "FLOAT","D8")
flow_acc.save(out_Workspace + "_flow_acc.tif")

# Raster Calculator
streams_raster = Con(flow_acc > 190000, 1,0)   # 1 for streams and 0 for non-streams
streams_raster.save(out_Workspace + "_streams_condn.tif")

# Stream to Feature
streams_con_fl = StreamToFeature(streams_raster, flow_dirn, out_Workspace + "_streams_con.shp", "SIMPLIFY")

# stream order
stream_order = StreamOrder(streams_raster, flow_dirn, "STRAHLER")
stream_order.save(out_Workspace + "_stream_order.tif")

stream_order_fl = StreamToFeature(stream_order, flow_dirn, out_Workspace + "_stream_order.shp", "SIMPLIFY")

# Select only 7th order streams
arcpy.management.MakeFeatureLayer(streams_con_fl, "streams_layer", "GRID_CODE = 4")
arcpy.management.CopyFeatures("streams_layer", out_Workspace + "_streams_4th_order.shp")

# Basin creation
basin = Basin(flow_dirn) 
basin.save(out_Workspace + "_basin.tif")

# Raster to polygon conversion
basin_poly = RasterToPolygon(basin, out_Workspace + "_basin_poly.shp")  # Convert the raster to polygon

#Process Calculate Areas...
# Add a new field to store area values
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

# Save the largest polygon to the output location
arcpy.CopyFeatures_management([largest_polygon], out_Workspace + "_largest_Basin.shp")
#------End------#

# Clip the DEM with the largest polygon
clip_raster(in_Dem, "#", out_Workspace+"_largest_Basin_Clipped.tif", largest_polygon)

#clip streams_con_fl with largest basin polygon
clip_featurelayer(streams_con_fl, largest_polygon, out_Workspace + "_clipped_streams_con_fl.shp")

#clip stream_order_fl with largest basin polygon
clip_featurelayer(stream_order_fl, largest_polygon, out_Workspace + "_clipped_stream_order_fl.shp")

# Refresh the map view after the process is complete
arcpy.RefreshActiveView()
arcpy.AddMessage("Process completed successfully and map view refreshed.")


# Give symbology to _clipped_stream_order_fl




#open layers after process complete function




