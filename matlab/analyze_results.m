function analyze_results(resultFolder)
% Load Python exports and generate MATLAB figures. No engine/toolbox needed.
% Usage: analyze_results('C:\path\results\single')
% Requires MATLAB R2020a or later (exportgraphics).
if nargin < 1
    resultFolder = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'results', 'single');
end
R = jsondecode(fileread(fullfile(resultFolder, 'result.json')));
keys = {'fixed','distance','combined'};
labels = {'Fixed layout','Distance objective','Risk-aware layout'};
colors = [0.51 0.57 0.66; 0.22 0.41 0.91; 0.03 0.62 0.54];
stats = cellfun(@(k) R.plans.(k).stats, keys, 'UniformOutput', false);
fig = figure('Color','w','Position',[80 80 1260 420]);
tiledlayout(1,3,'Padding','compact');
fields = {'mean_delivery','mean_exposure','total_distance'};
titles = {'Mean delivery time (s)','Exposure proxy per order','Total flight distance (km)'};
for j=1:3
    nexttile;
    values = cellfun(@(s) scalarOrNaN(s.(fields{j})), stats);
    if j==3, values = values/1000; end
    b = bar(values,'FaceColor','flat');
    b.CData = colors;
    xticks(1:3); xticklabels(labels); xtickangle(15);
    title(titles{j}); grid on;
end
sgtitle(sprintf('Synthetic simulation / evaluation seed %d',R.evaluation_seed));
exportgraphics(fig,fullfile(resultFolder,'matlab_comparison.png'),'Resolution',220);
exportgraphics(fig,fullfile(resultFolder,'matlab_comparison.pdf'),'ContentType','vector');

S = R.scene;
[X,Y] = meshgrid(0:8:S.width,0:8:S.height);
Z = 0.035*ones(size(X));
for i=1:numel(S.risk_zones)
    z = S.risk_zones(i);
    Z = Z + z.weight.*exp(-2.*((X-z.x).^2/z.rx^2+(Y-z.y).^2/z.ry^2));
end
Z = min(1,Z);
fig2 = figure('Color','w','Position',[120 100 1050 760]);
imagesc([0 S.width],[0 S.height],Z); axis equal tight; hold on;
set(gca,'YDir','reverse'); colormap(parula); colorbar; caxis([0 1]);
for i=1:numel(S.buildings)
    b=S.buildings(i);
    rectangle('Position',[b.x b.y b.w b.h],'FaceColor',[0.8 0.83 0.88],'EdgeColor',[0.4 0.5 0.6]);
end
if isstruct(S.closure)
    b=S.closure;
    rectangle('Position',[b.x b.y b.w b.h],'EdgeColor','r','LineStyle','--','LineWidth',2);
end
selected=string(R.plans.combined.pad_ids);
routes=struct2cell(R.routes);
for i=1:numel(routes)
    route=routes{i};
    if ~isstruct(route) || isempty(route.points), continue; end
    fromSelected=false;
    for p=1:numel(S.pads)
        pad=S.pads(p);
        if ismember(string(pad.id),selected) && norm(route.points(1,:)-[pad.x pad.y])<1e-6
            fromSelected=true;
        end
    end
    if fromSelected, plot(route.points(:,1),route.points(:,2),'-','Color',[0.1 0.5 0.9],'LineWidth',1); end
end
for i=1:numel(S.pads)
    p=S.pads(i);
    if ismember(string(p.id),selected)
        plot(p.x,p.y,'o','MarkerSize',11,'MarkerFaceColor',[0.03 0.62 0.54],'MarkerEdgeColor','w');
    else
        plot(p.x,p.y,'o','MarkerSize',6,'MarkerFaceColor','w','MarkerEdgeColor',[0.2 0.4 0.8]);
    end
    text(p.x+12,p.y,p.id,'FontWeight','bold');
end
for i=1:numel(S.deliveries)
    d=S.deliveries(i);
    plot(d.x,d.y,'d','MarkerFaceColor',[0.9 0.5 0.2],'MarkerEdgeColor','w');
end
xlabel('x (m)'); ylabel('y (m)');
title(sprintf('Synthetic exposure and routes / cruise altitude %.0f m',S.altitude));
exportgraphics(fig2,fullfile(resultFolder,'matlab_map.png'),'Resolution',220);
fprintf('Figures saved in %s\n',resultFolder);
fprintf('Exposure is a synthetic proxy, not an accident probability.\n');
end

function value=scalarOrNaN(value)
if isempty(value), value=NaN; end
end
